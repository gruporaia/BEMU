import os
from tqdm import tqdm
import google.generativeai as genai
import argparse
import json
import shutil
from utils import *

# ! =============== MAIN PARSING FUNCTIONS ===============

def parse_gabarito(sample_gabarito):
    # gather only part of table with answers
    isolated_answers = sample_gabarito.split('c|c|}\n\\hline\n')[1].split(' \\\\\n\\hline')[:-1]
    # isolate answer for each question + remove irrelevant latex symbols
    individual_answers = []
    individual_answers += sum([answer.split(' & ') for answer in isolated_answers], [])
    individual_answers = [answer.replace('\\hline\n', '').replace('$', '') for answer in individual_answers]
    # parse answers into dict with format {question_number: answer}
    parsed_gabarito = {}
    for answer in individual_answers:
        question_number = int(answer.split('-')[0])
        question_answer = answer.split('{')[1].replace('}', '')
        parsed_gabarito[question_number] = question_answer
    return parsed_gabarito

def parse_prova(prova_dir, sample_prova, year, gabarito):
    model = genai.GenerativeModel('models/gemini-1.5-flash-8b')
    prova = []
    sample_prova = apply_prefilter(sample_prova.split('\\begin{document}')[-1].replace('\n\n\n\\end{document}', ''))
    isolated_questions = sample_prova.replace('QUESTAO', 'QUESTÃO')\
        .replace('QUESTATO', 'QUESTÃO')\
        .replace('QUESTȦO', 'QUESTÃO')\
        .replace('QUESTÃ0', 'QUESTÃO')\
        .replace('QUESTĀO', 'QUESTÃO')\
        .replace('Questāo', 'QUESTÃO')\
        .replace('Questão', 'QUESTÃO')\
        .split('QUESTÃO')[1:]
    potetial_support_text = sample_prova.replace('QUESTAO', 'QUESTÃO')\
        .replace('QUESTATO', 'QUESTÃO')\
        .replace('QUESTȦO', 'QUESTÃO')\
        .replace('QUESTÃ0', 'QUESTÃO')\
        .replace('QUESTĀO', 'QUESTÃO')\
        .replace('Questāo', 'QUESTÃO')\
        .replace('Questão', 'QUESTÃO')\
        .split('QUESTÃO')[:1][0]
    # print(potetial_support_text)
    isolated_questions = remove_question_number_line(isolated_questions)
    # making sure we have the right amount of questions, if not manually fix the .tex doc
    if len(isolated_questions) != 90:
        raise ValueError(f'Expected 90 questions, found {len(isolated_questions)}, fix this error before proceeding')
    check_for_table(isolated_questions)
    check_includegraphics_occurrences(isolated_questions)
    check_alternatives_for_text_and_images(isolated_questions)
    check_all_alternatives_present(isolated_questions)
    check_support_text_present(isolated_questions)
    support_text_limit_idx = 0
    support_text = ''
    if find_specific_sentence(potetial_support_text):
        shared_question_intro = find_specific_sentence(potetial_support_text)[0]
        isolated_questions[0] = isolated_questions[0].split(shared_question_intro)[0]  
        support_text = potetial_support_text.split(shared_question_intro)[-1]
        support_text_limit_idx = find_last_number(shared_question_intro, 0)

    for idx, instance in tqdm(enumerate(isolated_questions)):
        questao = {
            'language': 'pt',
            'country': 'Brazil',
            'file_name': '',
            'source' : '',
            'license': 'Unknown',
            'level' : 'University Entrance',
            'category_en' : '',
            'category_original_lang' : '',
            'original_question_num' : -1,
            'question' : '',
            'options' : [],
            'answer' : '',
            'image_png' : '',
            'image_information' : None,
            'image_type' : None,
            'parallel_question_id' : None
        }
        # Add shared support text to all questions individually
        
        if support_text_limit_idx > 0:
            isolated_questions[idx] = support_text + instance
            if support_text_limit_idx == (idx+1):
                support_text_limit_idx = 0
                support_text = ''
        if find_specific_sentence(instance):
            shared_question_intro = find_specific_sentence(instance)[0]
            isolated_questions[idx] = instance.split(shared_question_intro)[0]  
            support_text = instance.split(shared_question_intro)[-1]
            support_text_limit_idx = find_last_number(shared_question_intro, idx+1)
        # get question text and image
        questao['question'], questao['image_png'] = separate_question_text_and_image(prova_dir, isolated_questions[idx], year, idx+1)
        # get question alternatives + convert to 4-answer format
        questao['original_question_num'] = idx+1
        questao['file_name'] = f"{prova_dir}{year}_1fase_prova"
        questao['source'] = SOURCE_DICT[year]
        questao['options'], questao['answer'] = extract_options(isolated_questions[idx], gabarito[idx+1])
        questao['options'] = parse_alternative_images(prova_dir, questao['options'], year, idx+1)
        if idx < 20:
            questao['category_original_lang'], questao['category_en'] = 'Língua Portuguesa', 'Portuguese Language'
        elif idx < 30:
            questao['category_original_lang'], questao['category_en'] = 'Inglês', 'English'
        else:
            questao['category_original_lang'], questao['category_en'] = prompt_gemini_subject(model, questao['question'])
        if questao['image_png']:
            questao['image_type'], questao['image_information'] = prompt_gemini_image(model, f"./{prova_dir}/{year}/new_images/{questao['image_png']}", questao['question'])
        prova.append(questao)

    return prova

def merge_json_files(prova_dir):
    merged_data = []
    for year in os.listdir(prova_dir):
        year_path = os.path.join(prova_dir, year)
        if os.path.isdir(year_path):
            with open(os.path.join(prova_dir, str(year), 'prova.json'), 'r') as file:
                data = json.load(file)
                print(type(data))
                merged_data += data
            src_images_dir = os.path.join(prova_dir, str(year), 'new_images/')
            shutil.copytree(src_images_dir, os.path.join(prova_dir, 'images/'), dirs_exist_ok = True)

    with open(os.path.join(prova_dir, 'data.json'), 'w') as outfile:
        json.dump(merged_data, outfile)

parser = argparse.ArgumentParser()
parser.add_argument('--prova_dir', help='Diretório em que as provas estão armazenadas seguindo a estrutura de pastas presente no README.')

def main() -> None:
    args = parser.parse_args()
    base_path = f'./{args.prova_dir}'
    data = {}
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=gemini_api_key)

    for year in tqdm(os.listdir(base_path)):
        year_path = os.path.join(base_path, year)
        if os.path.isdir(year_path):
            prova_path = os.path.join(year_path, 'prova.tex')
            gabarito_path = os.path.join(year_path, 'gabarito.tex')

            if os.path.exists(prova_path) and os.path.exists(gabarito_path):
                with open(prova_path, 'r') as prova_file:
                    prova_content = prova_file.read()
                with open(gabarito_path, 'r') as gabarito_file:
                    gabarito_content = gabarito_file.read()
                print(f"Parsing data for year {year}...")
                data[year] = {
                    'prova': parse_prova(args.prova_dir, prova_content, int(year), parse_gabarito(gabarito_content)),
                    'gabarito': parse_gabarito(gabarito_content)
                }
                save_list_of_dicts_to_json(data[year]['prova'], f'./{args.prova_dir}/{year}/prova.json')

    merge_json_files(args.prova_dir)

if __name__ == '__main__':
    main()