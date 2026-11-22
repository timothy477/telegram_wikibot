import requests
from bs4 import BeautifulSoup
import re


def getSoup(word, main_url, my_headers, url_=None):

    url = f"{main_url}{word}"
    if url_ != None:
        url = url_

    request = requests.get(url, headers=my_headers, stream=True)
    soup = BeautifulSoup(request.text, "lxml")

    return soup


# Получение определения
def getDefinition(soup):

    # Получаем все абзацы (теги p), чтобы потом проверить их на наличие
    ps = soup.find_all("p")

    definition = str()

    # Первый тег p, в котором будет тег b, считается определением
    for p in ps:
        if p.find("b") is not None:
            definition = p.text
            break

    # Удаление сносок ( [] )
    for d in definition:
        if d == "[":
            definition1 = definition[:definition.index(d)]
        elif d == "]":
            definition2 = definition[definition.index(d)+1:]
            definition = definition1 + definition2

    return definition


# Проверка на наличие ссылки на список значений слова
def otherDefinitions(soup):

    try:
        soup.find("div", class_=re.compile("hatnote navigation-not-searchable")).find("a").get("href")
        return True
    except:
        return False


# Получение ссылки на изображение (если оно есть)
def getImage(soup):

    try:
        image_url = soup.find("a", class_="mw-file-description").find("img", class_="mw-file-element").get("src")
    except AttributeError:

        try:
            image_url = soup.find("img", class_="mw-file-element").get("src")
        except AttributeError:
            return

    return image_url
