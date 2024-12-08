import os
import shutil
import time

def share_torrent_files(parent_folder):
    # Lấy danh sách tất cả các thư mục con trong parent_folder
    folders = [f for f in os.listdir(parent_folder) if os.path.isdir(os.path.join(parent_folder, f))]
    
    # Lọc chỉ lấy các folder có tên bắt đầu bằng "peer_"
    peer_folders = [folder for folder in folders if folder.startswith('peer_')]

    # Lặp qua các folder để tìm file .torrent
    for folder in peer_folders:
        folder_path = os.path.join(parent_folder, folder)
        # Kiểm tra xem có file .torrent trong folder này không
        for file_name in os.listdir(folder_path):
            if file_name.endswith('.torrent'):
                torrent_file_path = os.path.join(folder_path, file_name)
                
                # Sao chép file .torrent tới tất cả các folder peer_ còn lại
                for target_folder in peer_folders:
                    if target_folder != folder:  # Tránh sao chép file vào chính folder đó
                        target_folder_path = os.path.join(parent_folder, target_folder)
                        shutil.copy(torrent_file_path, target_folder_path)
                        print(f"Đã chia sẻ {file_name} từ {folder} đến {target_folder}")

if __name__ == "__main__":
    parent_folder = "C:/Users/ProTech247.vn/OneDrive/Máy tính/flask"  # Đặt đường dẫn đến thư mục cha của bạn ở đây

    while True:
        share_torrent_files(parent_folder)  # Gọi hàm chia sẻ file
        time.sleep(2)  # Đợi 2 giây trước khi kiểm tra lại
