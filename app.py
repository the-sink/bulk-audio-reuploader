import config
import uvicorn
import requests
import html
import os
import base64
import mimetypes
import json
from bs4 import BeautifulSoup
from tqdm import tqdm
from pathlib import Path
from typing import List
from fastapi import FastAPI, Request, Response, status

# welcome to my horrific spaghetti code, enjoy your stay

app = FastAPI()
session = requests.Session()

max_ids_per_request: int = 30
creator_type_translation = ["User", "Group"]
invalid_characters = '<>:"/\|?*'

uploaded_id_list = {}
temp_id_list = {}
current_place_id = 0
current_creator_id = 0
current_creator_type = 0
csrf_token = 0

if not os.path.isfile('uploaded_id_list.json'):
    with open('uploaded_id_list.json', 'w+') as f:
        json.dump({}, f)
        f.close()
else:
    with open('uploaded_id_list.json', 'r') as f:
        uploaded_id_list = json.load(f)
        f.close()

session.cookies.update({".ROBLOSECURITY": config.roblosecurity, ".RBXID": config.rbxid})

## UTILITY

def save_uploaded_id_list():
    with open('uploaded_id_list.json', 'w') as f:
        json.dump(uploaded_id_list, f)
        f.close()

def split_into_chunks(list, size):
    for i in range(0, len(list), size):
        yield list[i:i + size]

def get_group_owner(group_id: int):
    group_info = session.get("https://groups.roblox.com/v1/groups/" + str(group_id))

    if group_info.status_code == 200:
        return group_info.json().get('owner').get('userId')
    else:
        return -1

def get_neccesary_downloads(ids: List[int], game_creator_id: int, game_creator_type: str, place_id: int):
    global current_place_id
    global current_creator_id
    global current_creator_type
    global csrf_token

    current_place_id = place_id
    current_creator_id = game_creator_id
    current_creator_type = game_creator_type
    csrf_token = 0
    
    id_chunks = split_into_chunks(ids, max_ids_per_request)

    download_list = []
    group_owner_cache = {}

    pbar = tqdm(id_chunks)
    pbar.set_description("Determining neccesary downloads")

    for chunk in pbar:
        str_list = [str(int) for int in chunk]

        url = "https://apis.roblox.com/toolbox-service/v1/items/details?assetIds=" + ",".join(str_list)

        audio_info = session.get(url)

        if audio_info.status_code == 200:
            for item in audio_info.json()['data']:
                asset = item.get('asset')
                creator = item.get('creator')

                creator_id = creator.get('id')
                creator_type = creator_type_translation[creator.get('type')-1]

                if not asset.get('typeId') == 3: # Ignore assets that are not audio
                    continue

                if creator_id == 1 or creator_id == 1750384777: # Ignore Roblox and Monstercat accounts
                    continue

                if asset.get('duration') < 6: # Audio length qualifies it as a sound effect
                    continue

                if asset.get('name') == "(Removed for copyright)" or asset.get('name') == "[ Content Deleted ]": # Ignore audio that has been removed for copyright/moderated
                    continue
                
                download_list.append({"id": asset.get('id'), "name": asset.get('name')})
        else:
            pbar.write("Request error " + str(audio_info.status_code))

    if len(download_list) < 1:
        print("No assets have been detected that need to be reuploaded!")

    # obtain X-CSRF-TOKEN header in preparation for the upload process
    initial_request = session.post("https://publish.roblox.com/v1/audio")
    csrf_token = initial_request.headers.get("x-csrf-token")

    return download_list


### Gets a list of assets that need replacement


@app.post("/get-neccesary-downloads")
async def get_downloads(request: Request, creator_id: int, creator_type: str, place_id: int, response: Response):
    global temp_id_list
    temp_id_list = {}

    data = await request.json()

    response.status_code = status.HTTP_200_OK
    return get_neccesary_downloads(data, creator_id, creator_type, place_id)

### Downloads and re-uploads an asset

@app.post("/reupload")
async def reupload(asset_id: int, file_name: str, response: Response):
    page = session.get("https://www.roblox.com/library/" + str(asset_id))

    content = html.unescape(page.text)
    soup = BeautifulSoup(content, 'html.parser')

    button = soup.find('div', {'class': 'MediaPlayerIcon'})
    if button:
        url = button['data-mediathumb-url']
        audio_file = requests.get(url)
        file_extension = mimetypes.guess_extension(audio_file.headers['Content-Type'])
        #print(asset_id)
        #print(file_name)
        #print(audio_file.headers['Content-Type'])
        #print(file_extension)
        if file_extension == ".oga":
            file_extension = ".ogg"
        else:
            file_extension = ".mp3"

        file_name = file_name.replace("/", "")

        f = open("audio/" + file_name + file_extension, "wb")
        f.write(audio_file.content)
        f.close()

        

if __name__=="__main__":
    uvicorn.run("app:app", host='localhost', port=37007, workers=1)