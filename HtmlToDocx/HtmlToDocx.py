import requests
from bs4 import BeautifulSoup
import re
import json
import time
import os
import logging
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("script.log", mode='w', encoding='utf-8')
    ]
)

URL_firstPart = "http://suntd.kodeks.expert:1210/test/text?nd="
URL_secondPart = "&nh=0&print=1&links=1&save=1&origin=1"
pattern = re.compile(r'nd=(\d+)')

cookies = {
    'cookie_name': 'cookie_value'
}

with open('nd_values.txt', 'r') as file:
    nd_list = list(set(line.strip() for line in file))

logging.info(f"Удалены дублирующиеся значения ND. Оставлено {len(nd_list)} уникальных значений.")

DELAY = 1
MAX_RETRIES = 3
DOCUMENTS_PER_SESSION = 50

def sanitize_filename(filename):
    logging.info(f"Санитизация имени файла: {filename}")
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    filename = re.sub(r'\s+', " ", filename).strip()
    return filename[:100]

def fetch_url(session, url):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            logging.info(f"Запрос URL: {url}")
            response = session.get(url)
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError) as e:
            logging.warning(f"Ошибка при запросе {url}: {e}")
            retries += 1
            time.sleep(DELAY)
    logging.error(f"Не удалось получить доступ к {url} после {MAX_RETRIES} попыток.")
    return None

def create_session():
    logging.info("Создание новой сессии")
    session = requests.Session()
    session.cookies.update(cookies)
    return session

def save_document(data, directory, filename):
    sanitized_title = sanitize_filename(filename)
    filepath = os.path.join(directory, f"{sanitized_title}.json")
    
    if len(filepath) > 255:
        logging.warning(f"Пропущен файл с длинным путем: {filepath}")
        return
    
    logging.info(f"Сохранение документа: {filepath}")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def clean_text(text):
    return re.sub(r'[\s]+', ' ', text).strip()

def parse_content(content):
    questions, answer, justification = "", "", ""
    
    question_pattern = re.compile(r'Вопрос:(.*?)Ответ:', re.DOTALL)
    answer_pattern = re.compile(r'Ответ:(.*?)Обоснование:', re.DOTALL)
    justification_pattern = re.compile(r'Обоснование:(.*)', re.DOTALL)
    
    question_match = question_pattern.search(content)
    if question_match:
        questions = [q.strip() for q in question_match.group(1).split('?') if q.strip()]
    
    answer_match = answer_pattern.search(content)
    if answer_match:
        answer = answer_match.group(1).strip()
    
    justification_match = justification_pattern.search(content)
    if justification_match:
        justification = justification_match.group(1).strip()
    
    return questions, answer, justification

def process_document(session, nd, directory, is_nd_list=True):
    logging.info(f"Обработка документа nd={nd}")
    response = fetch_url(session, URL_firstPart + nd + URL_secondPart)
    if not response:
        logging.error(f"Не удалось получить страницу для nd={nd}.")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    document_title = soup.title.string if soup.title else "No Title"
    cleaned_title = clean_text(document_title)
    content = clean_text(soup.get_text(separator="\n", strip=True))
    
    if is_nd_list:
        questions, answer, justification = parse_content(content)
        data = {
            "document_title": cleaned_title,
            "question": questions,
            "answer": answer,
            "justification": justification
        }
    else:
        data = {
            'document_title': cleaned_title,
            'content': content
        }
    
    save_document(data, directory, cleaned_title)
    
    links = soup.find_all('a')
    nd_numbers = [pattern.search(link.get('href')).group(1) for link in links if link.get('href') and pattern.search(link.get('href'))]
    nd_numbers = list(set(nd_numbers))
    logging.info(f"Найдено {len(nd_numbers)} уникальных связанных документов для nd={nd}")
    
    return nd_numbers

spp_dir = 'СПП'
norma_dir = 'Норма'
os.makedirs(spp_dir, exist_ok=True)
os.makedirs(norma_dir, exist_ok=True)

session = create_session()
document_count = 0
all_related_nd_numbers = set()

# Прогресс-бар для основного списка nd_list
for nd in tqdm(nd_list, desc="Обработка nd_list"):
    if document_count >= DOCUMENTS_PER_SESSION:
        session = create_session()
        document_count = 0
        logging.info("Перезапуск сессии после выгрузки 50 документов.")

    nd_numbers = process_document(session, nd, spp_dir, is_nd_list=True)
    all_related_nd_numbers.update(nd_numbers)
    
    document_count += 1
    logging.info(f"Обработано документов: {document_count}")
    time.sleep(DELAY)

# Обработка всех уникальных связанных документов
for number in tqdm(all_related_nd_numbers, desc="Обработка связанных документов"):
    process_document(session, number, norma_dir, is_nd_list=False)
    time.sleep(DELAY)