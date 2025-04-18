import tkinter as tk
from tkinter import messagebox
import cloudscraper
from bs4 import BeautifulSoup
import os
import json
import edge_tts
import threading
import asyncio
import io
import pygame
import tempfile
import shutil
from datetime import datetime
import keyboard  # 新增引入 keyboard 模組
from pynput import keyboard  # 新增引入 pynput 模組
from scraper_factory import ScraperFactory  # 新增引入 ScraperFactory

# 新增：暫存紀錄檔案路徑
BOOKMARKS_FILE = 'bookmarks.json'

# Function to load chapter content from file

def load_chapter_content(novel_code, chapter_name):
    """
    從檔案中載入指定章節的內容。

    Args:
        novel_code (str): 小說代號。
        chapter_name (str): 章節名稱。

    Returns:
        str: 章節內容，若檔案不存在則返回 None。
    """
    content_file = os.path.join(novel_code, f'{chapter_name}.txt')
    if os.path.exists(content_file):
        with open(content_file, 'r', encoding='utf-8') as file:
            return file.read()
    return None

# Function to save chapter content to file

def save_chapter_content(novel_code, chapter_name, content):
    """
    將指定章節的內容儲存到檔案。

    Args:
        novel_code (str): 小說代號。
        chapter_name (str): 章節名稱。
        content (str): 要儲存的章節內容。
    """
    os.makedirs(novel_code, exist_ok=True)
    content_file = os.path.join(novel_code, f'{chapter_name}.txt')
    with open(content_file, 'w', encoding='utf-8') as file:
        file.write(content)

# Initialize pygame
pygame.init()
pygame.mixer.init()

# Variable to store the current chapter content
current_content = ''

# Variable to store the current TTS state
is_playing = False

# Variable to store the current line index
current_line_index = 0

# Dictionary to track TTS tasks for each line
tts_tasks = {}

# Dictionary to store preloaded audio data for each line
preloaded_audio = {}

# 新增全域背景任務字典
background_tasks = {}

# 新增全域暫存變數
next_chapter_cache = None

# Function to save line audio to file
def save_line_audio(novel_code, chapter_name, line_index, audio_data):
    """
    將指定行的音訊資料儲存到檔案。

    Args:
        novel_code (str): 小說代號。
        chapter_name (str): 章節名稱。
        line_index (int): 行索引。
        audio_data (bytes): 音訊資料。
    """
    os.makedirs(novel_code, exist_ok=True)
    audio_file = os.path.join(novel_code, f'{chapter_name}_{line_index}.mp3')
    with open(audio_file, 'wb') as file:
        file.write(audio_data)

# Function to load line audio from file
def load_line_audio(novel_code, chapter_name, line_index):
    """
    從檔案中載入指定行的音訊資料。

    Args:
        novel_code (str): 小說代號。
        chapter_name (str): 章節名稱。
        line_index (int): 行索引。

    Returns:
        str: 音訊檔案路徑，若檔案不存在則返回 None。
    """
    audio_file = os.path.join(novel_code, f'{chapter_name}_{line_index}.mp3')
    if os.path.exists(audio_file):
        return audio_file
    return None

# 
async def read_line_content(line_content, novel_code, chapter_name, line_index, rate='1.0'):
    """
    使用 TTS 生成指定行的音訊資料。

    Args:
        line_content (str): 行內容。
        novel_code (str): 小說代號。
        chapter_name (str): 章節名稱。
        line_index (int): 行索引。
        rate (str): 語速。

    Returns:
        bytes: 生成的音訊資料。
    """
    global is_playing  # 加入全域變數宣告
    tts = edge_tts.Communicate(line_content, voice_var.get(), rate=rate)
    audio_data = b''
    try:
        async for chunk in tts.stream():
            if not is_playing:
                return b''
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
    except edge_tts.exceptions.NoAudioReceived:
        # 當無音訊產生時，返回空位元組以忽略此行
        return b''
    return audio_data

# 
async def play_audio(audio_data, line_index):
    """
    播放指定的音訊資料。

    Args:
        audio_data (bytes): 音訊資料。
        line_index (int): 行索引。
    """
    global is_playing  # 加入全域變數宣告
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio_file:
        temp_audio_file.write(audio_data)
        audio_file = temp_audio_file.name
    pygame.mixer.music.load(audio_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy() and is_playing:
        await asyncio.sleep(0.1)
    if not is_playing:
        pygame.mixer.music.stop()

# Function to highlight the current line and move cursor to the start of the line
def highlight_and_move_cursor(line_index):
    """
    高亮顯示指定行，並將游標移動到該行的開頭。

    Args:
        line_index (int): 行索引。
    """
    chapter_content_text.tag_remove('highlight', '1.0', tk.END)
    start_index = f'{line_index + 1}.0'
    end_index = f'{line_index + 1}.end'
    chapter_content_text.tag_add('highlight', start_index, end_index)
    chapter_content_text.tag_config('highlight', background='yellow')
    chapter_content_text.mark_set(tk.INSERT, start_index)
    chapter_content_text.see(start_index)

# Function to get the current line index based on the cursor position
def get_current_line_index():
    """
    獲取當前游標所在的行索引。

    Returns:
        int: 當前行索引。
    """
    cursor_index = chapter_content_text.index(tk.INSERT)
    return int(cursor_index.split('.')[0]) - 1

# 
def preload_next_chapter_content():
    """
    預載下一章的內容，並暫存到全域變數中。
    """
    global next_chapter_cache
    current_selection = chapter_listbox.curselection()
    if current_selection and next_chapter_cache is None:
        next_index = current_selection[0] + 1
        if next_index < chapter_listbox.size():
            next_chapter_name = chapter_listbox.get(next_index)
            novel_code = novel_code_entry.get().strip()
            next_content = load_chapter_content(novel_code, next_chapter_name)
            if not next_content:
                chapter_url = chapters[next_chapter_name]
                scraper = ScraperFactory.get_scraper(radio_var.get())  # 使用 ScraperFactory
                next_content = scraper.scrape_chapter_content(novel_code, chapter_url)
                save_chapter_content(novel_code, next_chapter_name, next_content)
            next_chapter_cache = next_content

# 
async def _bg_preload_line(line_content, novel_code, chapter_name, line_index, rate):
    """
    背景預載指定行的音訊資料。

    Args:
        line_content (str): 行內容。
        novel_code (str): 小說代號。
        chapter_name (str): 章節名稱。
        line_index (int): 行索引。
        rate (str): 語速。
    """
    if line_content:
        audio = await read_line_content(line_content, novel_code, chapter_name, line_index, rate)
        preloaded_audio[line_index] = audio
        background_tasks.pop(line_index, None)

# 
def get_next_valid_indices(current_index, lines, count):
    """
    獲取從當前索引開始的下一個有效行索引。

    Args:
        current_index (int): 當前行索引。
        lines (list): 章節內容的行列表。
        count (int): 要獲取的有效行數。

    Returns:
        list: 有效行索引列表。
    """
    indices = []
    idx = current_index + 1
    while idx < len(lines) and len(indices) < count:
        if lines[idx].strip():
            indices.append(idx)
        idx += 1
    return indices

# 
async def read_chapter_content(rate='1.0'):
    """
    按行讀取章節內容並播放音訊。

    Args:
        rate (str): 語速。
    """
    global current_content, is_playing, current_line_index, preloaded_audio
    novel_code = novel_code_entry.get().strip()
    selection = chapter_listbox.curselection()
    if not selection:
        messagebox.showerror('Error', '請選擇一個章節。')
        is_playing = False
        toggle_tts_button.config(text='開始語音播放')
        return
    chapter_name = chapter_listbox.get(selection)
    lines = current_content.split('\n')
    
    # 確保第一行音頻已生成
    if lines and lines[0].strip():
        if not (preloaded_audio.get(0) and len(preloaded_audio[0]) > 0):
            preloaded_audio[0] = await read_line_content(lines[0].strip(), novel_code, chapter_name, 0, rate)
    
    while current_line_index < len(lines) and is_playing:
        line = lines[current_line_index].strip()
        if line:
            highlight_and_move_cursor(current_line_index)
            # 同步生成當前行音頻（若尚未生成）
            if not (preloaded_audio.get(current_line_index) and len(preloaded_audio[current_line_index]) > 0):
                preloaded_audio[current_line_index] = await read_line_content(line, novel_code, chapter_name, current_line_index, rate)
            audio_data = preloaded_audio.get(current_line_index)
            if audio_data and len(audio_data) > 0:
                await play_audio(audio_data, current_line_index)
        
        # 調度背景預載：取得下一個與下下一個有內容行數的索引
        next_indices = get_next_valid_indices(current_line_index, lines, 2)
        for preload_index in next_indices:
            if preload_index not in background_tasks and not (preloaded_audio.get(preload_index) and len(preloaded_audio[preload_index]) > 0):
                background_tasks[preload_index] = asyncio.create_task(
                    _bg_preload_line(lines[preload_index].strip(), novel_code, chapter_name, preload_index, rate)
                )
                
        current_line_index += 1

        # 當接近章節尾端時，預載下一章
        if auto_play_var.get() and current_line_index > 0.9 * len(lines):
            preload_next_chapter_content()
    
    if auto_play_var.get() and current_line_index >= len(lines):
        load_next_chapter_content()
        current_line_index = 0
        await read_chapter_content(rate)
    
    is_playing = False
    toggle_tts_button.config(text='開始語音播放')

# Function to update the speed label
def update_speed_label(value):
    """
    更新速度標籤的顯示。

    Args:
        value (str): 速度值。
    """
    speed_label.config(text=f'速度: {value}')

# Function to get the current speed from the slider
def get_current_speed():
    """
    獲取當前速度滑桿的值。

    Returns:
        float: 當前速度值。
    """
    return speed_slider.get()

# Function to convert speed value to percentage format with sign
def convert_speed_to_rate(speed):
    """
    將速度值轉換為百分比格式。

    Args:
        speed (float): 速度值。

    Returns:
        str: 百分比格式的速度。
    """
    rate = int((speed - 1.0) * 100)
    return f"{rate:+d}%"

# Function to start TTS playback in a separate thread with adjustable speed
def start_tts_thread():
    """
    在單獨的執行緒中啟動 TTS 播放。
    """
    global is_playing, current_line_index, preloaded_audio, current_content
    if not current_content:
        if chapter_listbox.size() > 0:
            chapter_listbox.selection_clear(0, tk.END)
            chapter_listbox.selection_set(0)
            display_chapter_content(None)
        else:
            messagebox.showerror("Error", "請先載入章節！")
            return
    is_playing = True
    preloaded_audio = {}  # 重置預加載資料
    current_line_index = get_current_line_index()
    toggle_tts_button.config(text='暫停語音播放')
    rate = convert_speed_to_rate(get_current_speed())
    tts_thread = threading.Thread(target=lambda: asyncio.run(read_chapter_content(rate)))
    tts_thread.start()

# 
def pause_tts():
    """
    暫停 TTS 播放，並自動新增暫存紀錄。
    """
    global is_playing  # 確保使用全域變數
    is_playing = False
    pygame.mixer.music.stop()
    toggle_tts_button.config(text='開始語音播放')
    add_bookmark()  # 自動新增暫存紀錄

# Function to start or pause TTS playback with adjustable speed
def toggle_tts():
    """
    切換 TTS 播放與暫停狀態。
    """
    global is_playing
    if is_playing:
        pause_tts()
    else:
        start_tts_thread()

# 
def on_press(key):
    """
    處理按鍵按下事件。

    Args:
        key: 按下的鍵。
    """
    try:
        if key.char == 'p':  # 假設 'p' 鍵用於播放/暫停
            # toggle_tts()
            return
    except AttributeError:
        if key == keyboard.Key.media_play_pause:
            toggle_tts()

def on_release(key):
    """
    處理按鍵釋放事件。

    Args:
        key: 釋放的鍵。
    """
    if key == keyboard.Key.esc:
        # Stop listener
        return False

listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()

# 
def load_next_chapter_content():
    """
    載入下一章的內容，並更新顯示。
    """
    global current_content, next_chapter_cache, preloaded_audio
    current_selection = chapter_listbox.curselection()
    if current_selection:
        next_index = current_selection[0] + 1
        if next_index < chapter_listbox.size():
            if next_chapter_cache:
                next_content = next_chapter_cache
                next_chapter_cache = None
            else:
                next_chapter_name = chapter_listbox.get(next_index)
                novel_code = novel_code_entry.get().strip()
                next_content = load_chapter_content(novel_code, next_chapter_name)
                if not next_content:
                    chapter_id = chapters[next_chapter_name]
                    scraper = ScraperFactory.get_scraper(radio_var.get())  # 使用 ScraperFactory
                    next_content = scraper.scrape_chapter_content(novel_code, chapter_id)
                    save_chapter_content(novel_code, next_chapter_name, next_content)
            preloaded_audio.clear()
            chapter_content_text.delete(1.0, tk.END)
            chapter_content_text.insert(tk.END, next_content)
            current_content = next_content
            chapter_listbox.selection_clear(0, tk.END)
            chapter_listbox.selection_set(next_index)
            chapter_listbox.activate(next_index)

# Global variable to store chapters
chapters = {}

# Function to load chapters and display in listbox
def load_chapters_ui():
    """
    載入章節列表並顯示在 UI 中。
    """
    global chapters, root
    novel_code = novel_code_entry.get().strip()
    if not novel_code:
        messagebox.showerror('Error', 'Please enter a novel code.')
        return
    scraper = ScraperFactory.get_scraper(radio_var.get())
    chapters = scraper.load_chapters(novel_code)
    if not chapters:
        chapters = scraper.scrape_chapters(novel_code)
    # 新增：更新視窗標題，顯示小說名稱
    novel_title = scraper.scrape_novel_title(novel_code)
    if (novel_title):
        root.title(f'小說抓取器 - {novel_title}')
    else:
        root.title('小說抓取器')
    chapter_listbox.delete(0, tk.END)
    for chapter_name in chapters:
        chapter_listbox.insert(tk.END, chapter_name)

# Function to clear all cached data
def clear_cache():
    """
    清除所有快取資料，包括章節與內容。
    """
    global chapters, preloaded_audio, next_chapter_cache
    chapters.clear()
    preloaded_audio.clear()
    next_chapter_cache = None
    chapter_listbox.delete(0, tk.END)
    chapter_content_text.delete(1.0, tk.END)

    # 刪除包含 chapters.json 的資料夾
    for folder_name in os.listdir('.'):
        folder_path = os.path.join('.', folder_name)
        if os.path.isdir(folder_path):  # 確保是資料夾
            chapters_file_path = os.path.join(folder_path, 'chapters.json')
            if os.path.exists(chapters_file_path):  # 檢查是否存在 chapters.json
                try:
                    shutil.rmtree(folder_path)  # 刪除資料夾
                except Exception as e:
                    messagebox.showerror("清除快取錯誤", f"無法刪除資料夾 {folder_name}：{e}")

    messagebox.showinfo("清除快取", "所有快取資料已清除！")

# Function to load and display chapter content

def display_chapter_content(event):
    """
    顯示選中的章節內容。

    Args:
        event: 事件物件。
    """
    selected_indices = chapter_listbox.curselection()
    if not selected_indices:
        return
    index = selected_indices[0]
    chapter_name = chapter_listbox.get(index)
    novel_code = novel_code_entry.get().strip()
    if not novel_code:
        messagebox.showerror('Error', '請先輸入小說代號！')
        return
    if chapter_name not in chapters:
        messagebox.showerror('Error', '章節不存在！')
        return
    content = load_chapter_content(novel_code, chapter_name)
    if not content:
        chapter_id = chapters.get(chapter_name)
        if chapter_id:
            scraper = ScraperFactory.get_scraper(radio_var.get())  # 使用 ScraperFactory
            content = scraper.scrape_chapter_content(novel_code, chapter_id)
            save_chapter_content(novel_code, chapter_name, content)
    chapter_content_text.delete(1.0, tk.END)
    chapter_content_text.insert(tk.END, content)
    chapter_content_text.mark_set(tk.INSERT, "1.0")  # 新增：將游標置於第一行最前面
    global current_content, current_line_index
    current_content = content
    current_line_index = 0
    chapter_content_text.tag_remove('highlight', '1.0', tk.END)
    # 保留 listbox 選取狀態，故不再重設 selection

# 讀取暫存紀錄
def load_bookmarks():
    """
    從檔案中載入暫存紀錄。

    Returns:
        list: 暫存紀錄列表。
    """
    if os.path.exists(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE, 'r', encoding='utf-8') as file:
            return json.load(file)
    return []

# 儲存暫存紀錄
def save_bookmarks(bookmarks):
    """
    將暫存紀錄儲存到檔案。

    Args:
        bookmarks (list): 暫存紀錄列表。
    """
    with open(BOOKMARKS_FILE, 'w', encoding='utf-8') as file:
        json.dump(bookmarks, file, ensure_ascii=False, indent=4)

# 更新暫存紀錄顯示
def update_bookmarks_display():
    """
    更新暫存紀錄的顯示。
    """
    bookmarks_listbox.delete(0, tk.END)
    for bookmark in bookmarks:
        display_text = f"{bookmark['novel_title']} - {bookmark['chapter']} - Line {bookmark['line']}"
        bookmarks_listbox.insert(tk.END, display_text)

# 新增暫存紀錄
def add_bookmark():
    """
    新增暫存紀錄，並更新顯示。
    """
    global bookmarks
    novel_code = novel_code_entry.get().strip()
    chapter_name = chapter_listbox.get(chapter_listbox.curselection())
    current_line = get_current_line_index()
    site = radio_var.get()
    scraper = ScraperFactory.get_scraper(site)  # 使用 ScraperFactory 獲取 scraper
    novel_title = scraper.scrape_novel_title(novel_code)
    bookmark = {
        'site': site,
        'novel_code': novel_code,
        'novel_title': novel_title,
        'chapter': chapter_name,
        'line': current_line
    }
    # 移除同一小說的舊紀錄
    bookmarks = [b for b in bookmarks if b['novel_code'] != novel_code]
    bookmarks.append(bookmark)
    if len(bookmarks) > 5:
        bookmarks.pop(0)
    save_bookmarks(bookmarks)
    update_bookmarks_display()

# 載入暫存紀錄點
def load_bookmark(event):
    """
    載入選中的暫存紀錄。

    Args:
        event: 事件物件。
    """
    global current_content, current_line_index
    selection = bookmarks_listbox.curselection()
    if not selection:
        return
    bookmark = bookmarks[selection[0]]
    novel_code_entry.delete(0, tk.END)
    novel_code_entry.insert(0, bookmark['novel_code'])
    radio_var.set(bookmark['site'])
    load_chapters_ui()
    chapter_listbox.selection_clear(0, tk.END)
    chapter_listbox.selection_set(chapter_listbox.get(0, tk.END).index(bookmark['chapter']))
    display_chapter_content(None)
    current_line_index = bookmark['line']
    highlight_and_move_cursor(current_line_index)

# 讀取暫存紀錄
bookmarks = load_bookmarks()

# Create the main window
root = tk.Tk()
root.title('小說抓取器')

top_frame = tk.Frame(root, height=150)
top_frame.pack(pady=5, fill=tk.X)

left_frame = tk.Frame(top_frame, width=300, height=900)
left_frame.place(x=20, y=0)
left_frame.grid_propagate(False)

source_label = tk.Label(left_frame, text='來源網站:')
source_label.grid(row=0, column=0, columnspan=2, pady=5)

radio_var = tk.StringVar(value="czbooks")
radio_button1 = tk.Radiobutton(left_frame, text="小說狂人", variable=radio_var, value="czbooks")
radio_button1.grid(row=1, column=0, sticky='w')
url_label1 = tk.Label(left_frame, text="小說狂人", fg="blue", cursor="hand2")
url_label1.grid(row=1, column=1, sticky='w')
url_label1.bind("<Button-1>", lambda e: os.system("start https://czbooks.net/"))

radio_button2 = tk.Radiobutton(left_frame, text="天天看小說", variable=radio_var, value="ttkan")
radio_button2.grid(row=2, column=0, sticky='w')
url_label2 = tk.Label(left_frame, text="天天看小說", fg="blue", cursor="hand2")
url_label2.grid(row=2, column=1, sticky='w')
url_label2.bind("<Button-1>", lambda e: os.system("start https://www.ttkan.co/"))

# 新增：中間區塊
middle_frame = tk.Frame(top_frame, width=500, height=120)
middle_frame.place(x=400, y=0)
middle_frame.grid_propagate(False) 

# Create the novel code entry and load button
novel_code_label = tk.Label(middle_frame, text='小說代號:')
novel_code_label.pack(pady=5, anchor='w')
novel_code_entry = tk.Entry(middle_frame)
novel_code_entry.pack(pady=5, anchor='w')
load_button = tk.Button(middle_frame, text='載入章節', command=load_chapters_ui)
load_button.pack(pady=5, anchor='s')
clear_cache_button = tk.Button(middle_frame, text='清除快取', command=clear_cache)
clear_cache_button.pack(pady=5, anchor='s')

# 新增：右側區塊
right_frame = tk.Frame(top_frame, width=300, height=120)
right_frame.place(x=600, y=0)
right_frame.grid_propagate(False)  # 禁止自動調整大小

bookmark_label = tk.Label(right_frame, text='暫存紀錄:')
bookmark_label.grid(row=0, column=0, pady=5)

bookmarks_listbox = tk.Listbox(right_frame, width=40, height=5)
bookmarks_listbox.grid(row=1, column=0, pady=5)
bookmarks_listbox.bind("<<ListboxSelect>>", load_bookmark)

update_bookmarks_display()

# Create the chapter listbox and content text widget with scrollbars
frame = tk.Frame(root)
frame.pack(pady=0, padx=10, fill=tk.BOTH, expand=True)

# Scrollbar for chapter listbox
chapter_listbox_scrollbar = tk.Scrollbar(frame)
chapter_listbox_scrollbar.pack(side=tk.LEFT, fill=tk.Y)

# 設定 exportselection=False 保持選取狀態
chapter_listbox = tk.Listbox(frame, width=40, exportselection=False, yscrollcommand=chapter_listbox_scrollbar.set)
chapter_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
chapter_listbox_scrollbar.config(command=chapter_listbox.yview)
# 新增：綁定章節點擊事件以載入內容
chapter_listbox.bind("<<ListboxSelect>>", display_chapter_content)

# Scrollbar for chapter content text widget
chapter_content_scrollbar = tk.Scrollbar(frame)
chapter_content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

chapter_content_text = tk.Text(frame, wrap=tk.WORD, yscrollcommand=chapter_content_scrollbar.set)
chapter_content_text.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
chapter_content_scrollbar.config(command=chapter_content_text.yview)

# Create the auto-play checkbox
auto_play_var = tk.BooleanVar()
auto_play_checkbox = tk.Checkbutton(root, text='自動播放下一章', variable=auto_play_var)
auto_play_checkbox.pack(pady=5)

# 新增：建立選項區塊，將速度與語音選項呈現為「說明在左，物件在右」
options_frame = tk.Frame(root)
options_frame.pack(pady=5)

# 速度列
speed_label = tk.Label(options_frame, text='速度:')
speed_label.grid(row=0, column=0, sticky='w', padx=5)
speed_slider = tk.Scale(options_frame, from_=0.5, to=1.5, resolution=0.25, orient=tk.HORIZONTAL, command=update_speed_label)
speed_slider.set(1.5)
speed_slider.grid(row=0, column=1, sticky='e', padx=5)

# 語音列
voice_options = ["zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural", "zh-TW-HsiaoChenNeural"]
voice_var = tk.StringVar(root, value="zh-CN-YunxiNeural")
voice_label = tk.Label(options_frame, text='選擇語音:')
voice_label.grid(row=1, column=0, sticky='w', padx=5)
voice_option_menu = tk.OptionMenu(options_frame, voice_var, *voice_options)
voice_option_menu.grid(row=1, column=1, sticky='e', padx=5)

# 修改：開始按鈕下方增加更多空間
toggle_tts_button = tk.Button(root, text='開始語音播放', command=toggle_tts)
toggle_tts_button.pack(pady=(5,20))

# Start the main event loop
root.mainloop()

# 新增：在主事件迴圈後，保持鍵盤監聽
listener.join()