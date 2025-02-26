import os
import json
import re
import google.generativeai as genai
from PIL import Image

# ! =============== GLOBAL VARIABLES ===============

SOURCE_DICT = {
    2014 : 'https://www.curso-objetivo.br/vestibular/resolucao-comentada/unesp/2014/1fase/UNESP2014_1fase_prova.pdf',
    2015 : 'https://www.curso-objetivo.br/vestibular/resolucao-comentada/unesp/2015/1fase/UNESP2015_1fase_prova.pdf',
    2016 : 'https://www.curso-objetivo.br/vestibular/resolucao-comentada/unesp/2016/1fase/UNESP2016_1fase_prova.pdf',
    2017 : 'https://www.curso-objetivo.br/vestibular/resolucao-comentada/unesp/2017/1fase/UNESP2017_1fase_prova.pdf',
}

ALTERNATIVE_DICT = {
    'A' : 0,
    'B' : 1,
    'C' : 2,
    'D' : 3,
    'E' : 4
}

# ! =============== HELPER FUNCTIONS ===============

def translate_subject(english_name):
    translations = {
        "History": "História",
        "Chemistry": "Química",
        "Geography": "Geografia",
        "Physics": "Física",
        "Biology": "Biologia",
        "Sociology": "Sociologia",
        "Philosophy": "Filosofia",
        "Mathematics": "Matemática",
        "Art History": "História da Arte",
    }
    return translations.get(english_name, "unknown")

def prompt_gemini_image(model, img_path, question_text):
    """Handles both image classification and importance assessment in a single request."""
    # model = genai.GenerativeModel('models/gemini-1.5-flash-8B')
    sample_file = genai.upload_file(path=img_path)

    text = f"""You are an advanced image classification assistant. Your task is:
    
    1. **Classify the image** into one of these categories:
       - 'graph': Data plotted on axes (line/bar charts, scatter plots, pie charts, flowcharts, etc.).
       - 'table': Structured data in rows and columns.
       - 'diagram': Schematic illustrations of processes, structures, or concepts.
       - 'scientific formula': Mathematical equations, chemical formulas, or math-related diagrams.
       - 'text': Images with mostly written content.
       - 'figure': Drawings or symbolic representations.
       - 'map': Geographical or spatial visualizations.
       - 'photo': Real-world photographic images.

    2. **Determine image importance** for answering this question:
       - **Essential**: The question requires specific visual details from the image, it would be IMPOSSIBLE to answer the question without the image (i.e. only using the text).
       - **Useful**: The image only provides extra context but is not necessary to answer the question.

    The question:
    {question_text}

    Answer format:
    
    Category:
    {{Category}}

    Importance:
    {{essential or useful}}
    """

    response = model.generate_content([text, sample_file]).text

    # Extracting data from response
    pattern = r'Category:\s*(.+)\s*\n+\s*Importance:\s*(.+)'
    matches = re.findall(pattern, response)
    
    if matches:
        image_type, img_importance = matches[0]
        image_type, img_importance = image_type.lower(), img_importance.lower()
    else:
        image_type, img_importance = ("unknown", "unknown")
    
    return image_type, img_importance

def prompt_gemini_subject(model, question_text):
    """Handles subject classification independently of images."""
    # model = genai.GenerativeModel('models/gemini-1.5-flash-8b')

    text = f"""You are a subject classification assistant. Your task is to determine:
    
    - The subject category of the question. Choose from: 
      **History, Chemistry, Geography, Physics, Biology, Sociology, Philosophy, Mathematics and Art History.**

    The question:
    {question_text}

    Answer format:

    Subject:
    {{subject option}}
    """

    response = model.generate_content(text).text

    # Extract subject
    pattern = r'Subject:\s*(.+)'
    match = re.search(pattern, response)

    subject_en = match.group(1) if match else "unknown"
    subject_pt = translate_subject(subject_en)

    return  subject_pt, subject_en

def find_specific_sentence(text):
    pattern = r'\bLeia\b.*?responder às questões.*?\.'
    matches = re.findall(pattern, text, re.IGNORECASE)
    return matches

def convert_list_elements_to_int(lst):
    return [int(element) for element in lst]

def find_last_number(sentence, current_question):
    pattern = r'\b\d+\b'
    matches = convert_list_elements_to_int(re.findall(pattern, sentence))
    last_number_pos = matches.index(current_question+1)+1
    return int(matches[last_number_pos])

def fix_itemize(text):
    # fix itemize environment
    text = text.replace('\\begin{itemize}', '').replace('\\end{itemize}', '').replace('  \\item', '-')
    return text

def fix_enumerate(text):
    # fix itemize environment
    text = text.replace('\\begin{enumerate}', '').replace('\\end{enumerate}', '')
    return text

def fix_center(text):
    # fix itemize environment
    text = text.replace('\\begin{center}', '').replace('\\end{center}', '')
    return text

def fix_hyphen(text):
    # fix hyphenation
    text = text.replace('--', '-')
    return text

def fix_ordinals(text):
    """
    # Example usage
    sample_text = "1o, 2@, 3응, 4ㅇ, and 5."
    modified_text = fix_ordinals(sample_text)
    print(modified_text)  # Output: "1º, 2º, 3º, 4º, and 5."
    """
    pattern = r'(\d)[o@응ㅇ]'
    modified_text = re.sub(pattern, r'\1º', text)
    return modified_text

def remove_latex_breaklines(text):
    # remove latex breaklines
    text = text.replace('\\\\\n', '\n')
    return text

def remove_section_tags(text):
    pattern = r'\\section\*\{(.*?)\}'
    modified_text = re.sub(pattern, r'\1', text)
    return modified_text

def remove_question_number_line(questions):
    return [text.split('\n', 1)[-1] for text in questions]

def apply_prefilter(text):
    text = remove_font_markers(text)
    text = remove_section_tags(text)
    text = fix_itemize(text)
    text = fix_enumerate(text)
    text = fix_center(text)
    text = remove_latex_breaklines(text)
    text = fix_hyphen(text)
    text = fix_ordinals(text)
    return text

def check_for_table(questions):
    """
    Check which questions (if any) have latex table in them,
    which should be replaced by images.
    """
    questions_to_fix = []
    for idx, question in enumerate(questions, 1):
        pattern = r'\\begin{tabular}'
        matches = re.findall(pattern, question)
        if matches:
            questions_to_fix.append(idx)
    if questions_to_fix:
        print(f"Questions with tables (need to be fixed): {questions_to_fix}")
        raise ValueError('Questions with tables found, fix this error before proceeding')

def check_includegraphics_occurrences(questions):
    """
    Check which questions (if any) have more than one image.
    """
    questions_to_fix = []
    for idx, question in enumerate(questions, 1):
        pattern = r'\\includegraphics'
        matches = re.findall(pattern, question.split('(A)')[0])
        if len(matches) > 1:
            questions_to_fix.append(idx)
    if questions_to_fix:
        print(f"Questions with more than one image (need to be fixed): {questions_to_fix}")
        raise ValueError('Questions with more than one image, fix this error before proceeding')

def check_alternatives_for_text_and_images(questions):
    """
    Check which questions (if any) have both images and text in the alternatives.
    """
    questions_to_fix = []
    for idx, question in enumerate(questions, 1):
        # pattern = r'\\includegraphics.*?\}'
        pattern = r'(?<!\\)\b\w+.*?\\includegraphics.*?\}'
        matches = re.findall(pattern, question.split('(A)')[-1].split('(B)')[0], re.DOTALL)
        if len(matches) >= 1:
            questions_to_fix.append(idx)
    if questions_to_fix:
        print(f"Questions both images and text in the alternatives: {questions_to_fix}")
        raise ValueError('Questions w/ both images and text in the alternatives, fix this error before proceeding')

def extract_alternatives_content(text):
    pattern = r'\((A|B|C|D|E)\)\s*(.*?)\s*(?=\(A\)|\(B\)|\(C\)|\(D\)|\(E\)|$)'
    matches = re.findall(pattern, text, re.DOTALL)
    alternatives = {match[0]: match[1].strip() for match in matches}
    return alternatives

def find_part_starting_with_E(text):
    pattern = r'\(E\).*?\n'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches

def parse_alternative_images(prova_dir, options, year, question_number):
    if find_includegraphics_string(options[0]):
        for idx, option in enumerate(options):
            image_filename = extract_filename_from_includegraphics(option)[0]
            image_filename = f"{image_filename}.jpg" if image_filename[:4] == '2025' else f"{image_filename}.png" 
            image_filename = process_image(prova_dir, os.path.join(prova_dir, f'/{year}/images/{image_filename}'), year, question_number)
            options[idx] = image_filename
    return options


def separate_question_text_and_image(prova_dir, question, year, question_number):
    image_filename = None
    question = question.split('(A)')[0].strip()
    image = find_includegraphics_string(question)
    if image:
        question = question.replace(image[0], '')
        image_filename = extract_filename_from_includegraphics(image[0])[0]
        image_filename = f"{image_filename}.jpg" if image_filename[:4] == '2025' else f"{image_filename}.png" 
        image_filename = process_image(prova_dir, os.path.join(prova_dir, f'/{year}/images/{image_filename}'), year, question_number)
    return question, image_filename


def extract_options(question, answer):
    options = list(extract_alternatives_content(question).values())
    if answer != 'E':
        options = options[:-1]
        answer = ALTERNATIVE_DICT[answer]
    else: 
        options = options[1:]
        answer = 3 # last index possible for 4-answer format
    return options, answer

def extract_filename_from_includegraphics(text):
    pattern = r'\\includegraphics.*?\{(.*?)\}'
    matches = re.findall(pattern, text)
    return matches

def find_includegraphics_string(text):
    pattern = r'\\includegraphics.*?\{.*?\}'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches 

def is_file_in_dir(dir_list, filename):
    for existing_file in dir_list:
        if filename in existing_file:
            print(filename)
            return existing_file
    return False

from PIL import Image

def process_image(prova_dir, image_path, year, question_number):
    # Ensure the new_images directory exists
    test_name = prova_dir.split('/')[-1].lower()
    new_images_dir = os.path.join(prova_dir, f'/{year}/new_images')
    os.makedirs(new_images_dir, exist_ok=True)
    dir_list = os.listdir(new_images_dir)
    # Extract the directory, filename, and extension
    directory, filename = os.path.split(image_path)
    name, ext = os.path.splitext(filename)
    file_exists = is_file_in_dir(dir_list, f"{name}.png")
    if file_exists:
        return file_exists
    else:
        # Check the extension and modify the filename accordingly
        if ext.lower() == '.jpg':
            new_filename = f"{test_name}_{year}_{question_number}_{name}.png"
        elif ext.lower() == '.png':
            if not name.startswith(f"{test_name}_{year}_"):
                new_filename = f"{test_name}_{year}_{question_number}_{name}.png"
            else:
                new_filename = filename
        else:
            raise ValueError("Unsupported file extension. Only .png and .jpg are allowed.")
        
        # Define the new image path
        new_image_path = os.path.join(new_images_dir, new_filename)
        # Move and rename the image
        img = Image.open(image_path)
        img.save(new_image_path)

        return new_filename

def check_all_alternatives_present(questions):
    """
    Check which questions (if any) have latex table in them,
    which should be replaced by images.
    """
    alternatives = ['(A)', '(B)', '(C)', '(D)', '(E)']
    questions_to_fix = []
    for idx, question in enumerate(questions, 1):
        for alternative in alternatives:
            if alternative not in question:
                questions_to_fix.append(idx)
    if questions_to_fix:
        print(f"Questions alternative text irregularities: {questions_to_fix}")
        raise ValueError('Questions with alternative text irregularities, fix this error before proceeding')

def check_text_after_alternative_e(text):
    pattern = r'\(E\).*?\n(.*)'
    match = re.search(pattern, text, re.DOTALL)
    return match

def check_support_text_present(questions):
    """
    Check which questions (if any) have more than one image.
    """
    questions_to_fix = []
    for idx, question in enumerate(questions, 1):
        match = check_text_after_alternative_e(question)
        # print(match.group(1).strip())
        # quit(1)
        if match and match.group(1).strip():
            questions_to_fix.append(idx)
    if questions_to_fix:
        print(f"Warning: potential questions with support text (might need to be fixed): {questions_to_fix}")
        print(f"If support text is indeed present make sure it starts with 'Leia', otherwise leave it as is.")

def save_list_of_dicts_to_json(list_of_dicts, filename):
    with open(filename, 'w') as json_file:
        json.dump(list_of_dicts, json_file, indent=4)

def remove_font_markers(text):
    return text.replace('[0pt]', '')