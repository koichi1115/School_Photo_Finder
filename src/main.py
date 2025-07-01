import json
import time
import os
import face_recognition
import requests
from io import BytesIO
from PIL import Image
import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def load_target_faces(image_dir):
    """指定されたディレクトリからターゲットの顔画像を読み込み、エンコーディングを生成する"""
    known_face_encodings = []
    known_face_names = []

    for filename in os.listdir(image_dir):
        if filename.endswith((".jpg", ".png")):
            image_path = os.path.join(image_dir, filename)
            print(f"ターゲット画像を読み込み中: {image_path}")
            image = face_recognition.load_image_file(image_path)
            face_encodings = face_recognition.face_encodings(image)
            if face_encodings:
                known_face_encodings.append(face_encodings[0])
                known_face_names.append(os.path.splitext(filename)[0]) # ファイル名を名前として使用
            else:
                print(f"警告: {filename} から顔を検出できませんでした。")
    return known_face_encodings, known_face_names

def load_credentials(config_path):
    """設定ファイルから認証情報を読み込む"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config['login_id'], config['password']
    except FileNotFoundError:
        print(f"エラー: 設定ファイルが見つかりません: {config_path}")
        return None, None
    except json.JSONDecodeError:
        print(f"エラー: 設定ファイルの内容が正しいJSON形式ではありません: {config_path}")
        return None, None
    except KeyError:
        print(f"エラー: 設定ファイルに 'login_id' または 'password' のキーがありません。")
        return None, None

def download_image(url):
    """URLから画像をダウンロードする"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる
        return Image.open(BytesIO(response.content))
    except requests.exceptions.RequestException as e:
        print(f"画像のダウンロード中にエラーが発生しました: {url} - {e}")
        return None
    except Exception as e:
        print(f"画像の読み込み中にエラーが発生しました: {url} - {e}")
        return None

def main():
    """メインの処理を実行する"""
    # --- パスの設定 ---
    # このスクリプト(main.py)があるディレクトリの絶対パスを取得
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # config.jsonへの絶対パスを構築
    config_path = os.path.join(script_dir, 'config.json')

    # --- 認証情報の読み込み ---
    login_id, password = load_credentials(config_path)
    if not all([login_id, password]) or 'YOUR_ID_HERE' in login_id:
        print("処理を中断します。src/config.json に正しいIDとパスワードを設定してください。")
        return

    # --- ターゲット顔写真の読み込み ---
    image_dir = os.path.join(script_dir, 'images')
    known_face_encodings, known_face_names = load_target_faces(image_dir)
    if not known_face_encodings:
        print("エラー: ターゲットとなる顔写真が見つからないか、顔を検出できませんでした。")
        return

    # --- WebDriverのセットアップ ---
    driver = webdriver.Chrome()
    login_url = "https://ps.happysmile-inc.jp/sys/UserLogin"

    try:
        print(f"{login_url} を開いています...")
        driver.get(login_url)

        # --- ログイン処理 ---
        # 注意: 以下のIDは実際のサイトに合わせて変更する必要があります。
        # ブラウザの開発者ツール（F12キー）を使い、入力欄の正しいIDやname属性を確認してください。
        USERNAME_FIELD_XPATH = "//*[@id=\"mail\"]"  # 実際のXPath
        PASSWORD_FIELD_XPATH = "//*[@id=\"password\"]"  # 実際のXPath
        LOGIN_BUTTON_XPATH = "//*[@id=\"loginArea\"]/div/div[6]/input" # 実際のXPath

        print("ログイン情報を入力しています...")
        # ユーザーID入力欄が表示されるまで最大10秒待機
        wait = WebDriverWait(driver, 10)
        username_field = wait.until(EC.presence_of_element_located((By.XPATH, USERNAME_FIELD_XPATH)))
        password_field = driver.find_element(By.XPATH, PASSWORD_FIELD_XPATH)

        username_field.send_keys(login_id)
        password_field.send_keys(password)

        # ログインボタンをクリック
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, LOGIN_BUTTON_XPATH)))
        driver.execute_script("arguments[0].click();", login_button)

        print("ログインしました。ログイン後のページを10秒間表示します...")
        time.sleep(10) # ログインが成功したか目視で確認するために待機
        

        # --- 展示室の選択 ---
        print("展示室一覧を読み込み中...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "roomList")))
        room_table = driver.find_element(By.CLASS_NAME, "roomList")
        rows = room_table.find_elements(By.TAG_NAME, "tr")

        available_rooms = []
        for row in rows[1:]:  # ヘッダー行をスキップ
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) > 3: # 少なくともご注文状況の列があることを確認
                title_element = row.find_element(By.CSS_SELECTOR, "th[data-subtitle='展示室タイトル'] a")
                order_status_element = row.find_element(By.CSS_SELECTOR, "td[data-subtitle='ご注文状況'] span")

                room_title = title_element.text
                room_href = title_element.get_attribute("href")
                order_status = order_status_element.text

                if order_status != "購入済":
                    available_rooms.append({"title": room_title, "href": room_href, "status": order_status})

        if not available_rooms:
            print("処理可能な展示室が見つかりませんでした。")
            return

        print("\n処理する展示室を選択してください:")
        for i, room in enumerate(available_rooms):
            print(f"{i + 1}. {room['title']} (状況: {room['status']})")

        selected_index = -1
        while not (0 <= selected_index < len(available_rooms)):
            try:
                selected_index = int(input("番号を入力してください: ")) - 1
                if not (0 <= selected_index < len(available_rooms)):
                    print("無効な番号です。再度入力してください。")
            except ValueError:
                print("無効な入力です。数字を入力してください。")

        selected_room = available_rooms[selected_index]
        print(f"'{selected_room['title']}' を選択しました。")

        # 選択した展示室のリンクをクリック
        print(f"展示室 '{selected_room['title']}' に移動します...")
        driver.get(selected_room['href'])

        # --- 「写真はこちら」ボタンのクリック ---
        print("「写真はこちら」ボタンを探しています...")
        photo_button_xpath = '//*[@id="categoryBtn"]/span'
        photo_button = wait.until(EC.element_to_be_clickable((By.XPATH, photo_button_xpath)))
        driver.execute_script("arguments[0].click();", photo_button)
        print("「写真はこちら」ボタンをクリックしました。")

        # --- 日付選択ボタンのクリック ---
        print("日付選択ボタンを探しています...")
        # 日付選択ボタンのXPathは提供されていないため、仮のXPathを使用します。
        # 実際のサイトに合わせて修正が必要です。
        date_select_button_xpath = "//a[@class='active']" # 実際のXPath
        date_select_button = wait.until(EC.element_to_be_clickable((By.XPATH, date_select_button_xpath)))
        driver.execute_script("arguments[0].click();", date_select_button)
        print("日付選択ボタンをクリックしました。")

        # --- フォルダ（アルバム）の選択 ---
        print("フォルダ一覧を読み込み中...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.open")))
        folder_elements = driver.find_elements(By.CSS_SELECTOR, "a.open")

        available_folders = []
        for folder_element in folder_elements:
            folder_title = folder_element.text
            folder_href = folder_element.get_attribute("href")
            available_folders.append({"title": folder_title, "href": folder_href})

        if not available_folders:
            print("処理可能なフォルダが見つかりませんでした。")
            return

        print("\n処理するフォルダを選択してください:")
        for i, folder in enumerate(available_folders):
            print(f"{i + 1}. {folder['title']}")

        selected_index = -1
        while not (0 <= selected_index < len(available_folders)):
            try:
                selected_index = int(input("番号を入力してください: ")) - 1
                if not (0 <= selected_index < len(available_folders)):
                    print("無効な番号です。再度入力してください。")
            except ValueError:
                print("無効な入力です。数字を入力してください。")

        selected_folder = available_folders[selected_index]
        print(f"'{selected_folder['title']}' を選択しました。")

        # 選択したフォルダのリンクをクリック
        print(f"フォルダ '{selected_folder['title']}' に移動します...")
        driver.get(selected_folder['href'])

        # --- 写真の顔認証と候補追加の処理 ---
        print("写真の顔認証を開始します...")
        # ページが完全にロードされるのを待つ
        wait.until(EC.presence_of_element_located((By.ID, "photoListInner")))

        photo_boxes = driver.find_elements(By.CSS_SELECTOR, ".photoBox.photo")
        print(f"{len(photo_boxes)} 枚の写真が見つかりました。")

        for i, photo_box in enumerate(photo_boxes):
            try:
                # 画像URLの抽出
                image_frame = photo_box.find_element(By.CLASS_NAME, "image-frame")
                style = image_frame.get_attribute("style")
                # background-image:url("...") からURLを抽出
                image_url = style.split('url("')[1].split('")')[0]
                
                # 画像のダウンロード
                photo_image = download_image(image_url)
                if photo_image is None:
                    print(f"写真 {i+1}/{len(photo_boxes)}: 画像のダウンロードに失敗しました。スキップします。")
                    continue

                # PIL Imageをnumpy arrayに変換
                photo_image_np = np.array(photo_image)

                # 写真から顔を検出
                face_locations = face_recognition.face_locations(photo_image_np)
                face_encodings = face_recognition.face_encodings(photo_image_np, face_locations)

                found_face = False
                for face_encoding in face_encodings:
                    # ターゲットの顔と比較
                    matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                    
                    if True in matches:
                        first_match_index = matches.index(True)
                        matched_name = known_face_names[first_match_index]
                        print(f"写真 {i+1}/{len(photo_boxes)}: ターゲットの顔 ({matched_name}) を検出しました。")

                        # 「ご注文候補に追加」ボタンをクリック
                        # ボタンのIDは photoBox の id から推測できる
                        photo_id = photo_box.get_attribute("id")
                        add_button_xpath = f"//*[@id='cb1_{photo_id}']"
                        
                        add_button = wait.until(EC.element_to_be_clickable((By.XPATH, add_button_xpath)))
                        driver.execute_script("arguments[0].click();", add_button)
                        print(f"写真 {i+1}/{len(photo_boxes)}: 「ご注文候補に追加」ボタンをクリックしました。")
                        found_face = True
                        break # 1つでも顔が見つかれば次の写真へ

                if not found_face:
                    print(f"写真 {i+1}/{len(photo_boxes)}: ターゲットの顔は検出されませんでした。")

            except Exception as e:
                print(f"写真 {i+1}/{len(photo_boxes)} の処理中にエラーが発生しました: {e}")
            
            time.sleep(0.5) # サーバーへの負荷軽減のため少し待機
        
        print("すべての写真の顔認証と候補追加処理が完了しました。")
        time.sleep(5) # 処理結果を確認するために少し待機

    except Exception as e:
        print(f"エラーが発生しました: {e}")

    finally:
        print("ブラウザを終了します。")
        driver.quit()

if __name__ == "__main__":
    main()
