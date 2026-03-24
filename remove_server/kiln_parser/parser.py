import cv2
import pytesseract
import json
import os
import shutil
import time

def parse_by_cells(image_path):
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image {image_path} not found")
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    
    # Папка для отладки
    folder = 'debug_cells'
    if os.path.exists(folder):
        shutil.rmtree(folder)
        time.sleep(2)

    os.makedirs(folder)
    

    # 1. Поиск строк (упрощенно по проекции или линиям)
    # Для отладки можно задать шаг вручную, если сетка не находится
    # Пример: фиксированный шаг строки ~25 пикселей, начиная с 50
    start_y = 64
    row_height = 17 
    total_rows = 26
    
    # Границы столбцов (в пикселях или %). Лучше подобрать вручную по сохраненным картинкам
    # Примерные координаты для вашего скриншота (нужно уточнить)
    col_ranges = [
        (10, 52),  # ЗОНА
        (100, 140),  # КТ
        (169, 205),  # ПКТ
        (238, 270),  # ИЗМ
        (305, 333),  # ОШИБ
        (372, 410)   # ВЫКЛ
    ]
    
    result = []
    config = r'-l eng --psm 7 -c tessedit_char_whitelist=0123456789,.-'
    
    for i in range(total_rows):
        y1 = start_y + i * row_height + 2
        y2 = y1 + row_height - 2
        
        row_data = {}
        valid_row = True
        
        for idx, (x_start_pct, x_end_pct) in enumerate(col_ranges):
            x1 = x_start_pct
            x2 = x_end_pct
            
            # Вырезка ячейки
            cell = gray[y1:y2, x1:x2]
            
            # Сохранение для отладки
          #  cv2.imwrite(f"debug_cells/row_{i}_col_{idx}.png", cell)
            
            # OCR
            text = pytesseract.image_to_string(cell, config=config).strip()
            
            try:
                val = float(text.replace(',', '.'))
            except:
                val = 0
            row_data[idx] = val
        print(*row_data.values())
        if valid_row and len(row_data) == 6:
            result.append({
                "ЗОНА": int(row_data[0]), "КТ": row_data[1], "ПКТ": row_data[2],
                "ИЗМ": row_data[3], "ОШИБКА": row_data[4], "ВЫКЛ": int(row_data[5])
            })

    return json.loads(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    try:
        json_data = parse_by_cells("screen_2026-03-18_13-43-28.png")
        print(json_data)
        with open("output.json", "w", encoding="utf-8") as f:
            f.write(json_data)
    except Exception as e:
        print(f"Error: {e}")