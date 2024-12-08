import requests
import random
import argparse
import hashlib
import os
import time
from tqdm import tqdm
from threading import Thread
import threading
import socket
from bencodepy import encode as bencode, decode as bdecode

files = []

class Peer:
    def __init__(self, peer_id, tracker_host, peer_host, tracker_port=8000):
        self.peer_id = peer_id
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.peer_host = peer_host
        self.peer_port = random.randint(10000, 20000)
        self.files = []  # Danh sách file mà peer đang quản lý
        self.shared_pieces = {}

    def notify_tracker_seeding(self, file_name, flag):
        """ Thông báo tracker rằng peer đang seeding """
        url = f'http://{self.tracker_host}:{self.tracker_port}/seeding'
        data = {
            'peer_host': self.peer_host,
            'peer_port': self.peer_port,
            'peer_id': self.peer_id,
            'filename': file_name,
            'flag':flag
        }
        requests.post(url, json=data)

    def notify_tracker_downloading(self, file_name, flag):
        """ Thông báo tracker rằng peer đang leeching """
        url = f'http://{self.tracker_host}:{self.tracker_port}/leeching'
        data = {
            'peer_host': self.peer_host,
            'peer_port': self.peer_port,
            'peer_id': self.peer_id,
            'filename': file_name,
            'flag':flag
        }
        requests.post(url, json=data)
        
    def connect_to_tracker(self):
        """ Đăng ký peer với tracker """
        url = f'http://{self.tracker_host}:{self.tracker_port}/connect'
        data = {
            'peer_id': self.peer_id,
            'peer_host': self.peer_host,
            'peer_port': self.peer_port
        }
        response = requests.post(url, json=data)
        self.print_response(response)

    def disconnect_from_tracker(self):
        """ Ngắt kết nối peer với tracker """
        url = f'http://{self.tracker_host}:{self.tracker_port}/disconnect'
        data = {
            'peer_id': self.peer_id,
            'peer_host': self.peer_host,
            'peer_port': self.peer_port
        }
        response = requests.post(url, json=data)
        self.print_response(response)

    def print_response(self, response):
        """ In thông tin phản hồi từ tracker """
        try:
            response_data = response.json()
            print(f"Status: {response_data.get('status')}")
            print(f"Action: {response_data.get('message')}")
        except Exception:
            print(f"Failed to parse response: {response.text}")

    def create_torrent_file(self, filename):
        """Tạo file torrent từ file hiện có"""
        dir = f"peer_{self.peer_id}"
        full_output_path = os.path.join(dir, filename)

        if not os.path.exists(full_output_path):
            print("File not found in the directory to create a torrent file!")
            return

        piece_length = 256 * 1024  # 256 KB per piece
        file_size = os.path.getsize(full_output_path)
        num_pieces = (file_size + piece_length - 1) // piece_length  # Tính số lượng phần

        # SHA1 hash mỗi phần của file
        pieces = b''
        
        progress_bar = tqdm(total=num_pieces, unit='piece', desc='Creating torrent', leave=True)
        try:
            with open(full_output_path, 'rb') as file:
                for _ in range(num_pieces):
                    piece = file.read(piece_length)
                    pieces += hashlib.sha1(piece).digest()
                    progress_bar.update(1)
        finally:
            progress_bar.close()

        # Metadata cho torrent
        tracker_url = f'http://{self.tracker_host}:{self.tracker_port}/peer_list'
        metadata = {
            'peer_list': tracker_url,
            'info': {
                'name': filename,
                'length': file_size,
                'piece length': piece_length,
                'pieces': pieces,
            }
        }
        bencoded_data = bencode(metadata)

        torrent_filename = f"{filename}.torrent"
        torrent_path = os.path.join(dir, torrent_filename)
        try:
            with open(torrent_path, 'wb') as torrent_file:
                torrent_file.write(bencoded_data)
        except Exception as e:
            print(f"Error writing torrent file: {e}")
            return

        print(f"Torrent file {torrent_filename} created successfully!")

    def upload_info_hash_to_tracker(self, filename):
        """Gửi thông tin hash của torrent file lên tracker"""
        dir = f"peer_{self.peer_id}"
        full_output_path = os.path.join(dir, filename)

        if not os.path.exists(full_output_path):
            print("File not found in directory!")
            return

        torrent_filename = f"{filename}.torrent"
        torrent_path = os.path.join(dir, torrent_filename)
        if not os.path.exists(torrent_path):
            print("Create torrent file before uploading!")
            return

        try:
            with open(torrent_path, 'rb') as file:
                metadata = bdecode(file.read())
                bencoded_info = bencode(metadata[b'info'])
        except Exception as e:
            print(f"Error reading torrent file: {e}")
            return
        
        files.append({'filename': filename, 'pieces': metadata[b'info'][b'pieces']})
        headers = {'Content-Type': 'application/json'}
        data = {
            'command': 'upload info',
            'peer_host': self.peer_host,
            'peer_port': self.peer_port,
            'peer_id': self.peer_id,
            'filename': filename,
            'info_hash': hashlib.sha1(bencoded_info).hexdigest()
        }

        tracker_url = f'http://{self.tracker_host}:{self.tracker_port}/info_hash'
        try:
            response = requests.post(tracker_url, json=data, headers=headers)
            self.print_response(response)
        except Exception as e:
            print(f"Failed to connect to tracker: {e}")

    def send_file_piece(self, client_socket, file_name, piece_index, piece_size, file_pieces):
        """Gửi một mảnh dữ liệu cho client"""
        offset = piece_index * piece_size
        if piece_index < len(file_pieces):
            dir = f"peer_{self.peer_id}"
            full_output_path = os.path.join(dir, file_name)
            with open(full_output_path, 'rb') as file:
                file.seek(offset)
                piece_data = file.read(piece_size)
                if piece_data:
                    client_socket.sendall(piece_data)
                else:
                    print("No data read from file; possible end of file.")
        else:
            print(f"Piece index {piece_index} is out of range.")

    def start_seeder_server(self):
        """Khởi động server seeding"""
        
        def client_handler(client_socket, addr):
            
            try:
                data = client_socket.recv(1024).decode()
                if data:
                    
                    piece_index, filename, peer_id, peer_host, peer_port = data.split(',')
                    piece_index = int(piece_index)
                    peer_info = {
                        'peer_id': peer_id,
                        'peer_host': peer_host,
                        'peer_port': int(peer_port),
                    }
                    if peer_port not in self.shared_pieces:
                        self.shared_pieces[peer_port] = {}

                    if filename not in self.shared_pieces[peer_port]:
                        self.shared_pieces[peer_port][filename] = []
                        
                    self.notify_tracker_seeding(file_name=filename, flag="start")
                    
                    # Tìm và gửi mảnh dữ liệu
                    for file in files:
                        if file['filename'] == filename:
                            file_pieces = file['pieces']
                                
                            if piece_index not in self.shared_pieces[peer_port][filename]:
                                # Gửi mảnh dữ liệu cho peer
                                self.send_file_piece(client_socket, filename, piece_index, 256 * 1024, file_pieces, peer_info)
                                self.shared_pieces[peer_port][filename].append(piece_index)
                                print(f"Sent piece index {piece_index} to peer {peer_info['peer_id']}") 
                            else:
                                print(f"Piece {piece_index} already shared with peer {peer_info['peer_id']}. Skipping.")
            except Exception as e:
                print(f"Error handling client: {e}")
            finally:
                # if filename:
                #     self.notify_tracker_seeding(file_name=filename, flag="end")
                    
                client_socket.close()

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.peer_host, self.peer_port))
        server_socket.listen(5)
        print(f"Seeder listening on {self.peer_host}:{self.peer_port}")

        while True:
            client_socket, addr = server_socket.accept()
            Thread(target=client_handler, args=(client_socket, addr), daemon=True).start()

    def download_torrent(self, torrent_filename):
        """Tải file từ torrent"""
        dir = f"peer_{self.peer_id}"
        full_output_path = os.path.join(dir, torrent_filename)

        if not os.path.exists(full_output_path):
            print("You don't have the torrent file in the directory!")
            return

        with open(full_output_path, 'rb') as file:
            torrent_data = bdecode(file.read())
            tracker_url = torrent_data[b'peer_list'].decode()
            info_hash = hashlib.sha1(bencode(torrent_data[b'info'])).hexdigest()
            filename = torrent_data[b'info'][b'name'].decode()

        all_hashes = torrent_data[b'info'][b'pieces']
        hash_length = 20  # SHA-1 hashes are 20 bytes long
        num_pieces = len(all_hashes) // hash_length
        piece_length = torrent_data[b'info'][b'piece length']

        validated_pieces = [None] * num_pieces
        peer_idx = 0
        i = 0

        self.notify_tracker_downloading(file_name = torrent_filename.rsplit('.torrent', 1)[0], flag = "start")

        while i < num_pieces:
            # Contact the tracker to get peers
            message = {
                'command': 'peer_list',
                'info_hash': info_hash
            }
            try:
                response = requests.get(tracker_url, json=message)
                if response.ok:
                    data = response.json()
                    if data['status'] == 'success':
                        print("Peers holding the file:", data['peers'])
                    else:
                        print("No peers found or error:", data['message'])
                        break
                else:
                    print("Failed to contact tracker:", response.status_code)
                    return
            except Exception as e:
                print(f"Failed to connect to tracker: {e}")
                return

            number_of_peers = len(data['peers'])
            while number_of_peers == 0:
                print("No peers found. Trying again in 5 seconds.")
                time.sleep(5)
                try:
                    response = requests.post(tracker_url, json=message)
                    if response.ok:
                        data = response.json()
                        if data['status'] == 'success':
                            print("Peers holding the file:", data['peers'])
                            number_of_peers = len(data['peers'])
                        else:
                            print("No peers found or error:", data['message'])
                    else:
                        print("Failed to contact tracker:", response.status_code)
                except Exception as e:
                    print(f"Failed to connect to tracker: {e}")
                    return

            if peer_idx >= number_of_peers:
                peer_idx = 0
            seeder_host = data['peers'][peer_idx]['peer_host']
            seeder_port = int(data['peers'][peer_idx]['peer_port'])

            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client_socket.connect((seeder_host, seeder_port))
            except ConnectionRefusedError:
                print(f"Failed to connect to {seeder_host}:{seeder_port}, trying next peer.")
                peer_idx += 1
                if peer_idx == number_of_peers:
                    peer_idx = 0
                time.sleep(5)
                continue

            peer_idx += 1
            if peer_idx == number_of_peers:
                peer_idx = 0

            client_socket.send(f"{i},{filename},{self.peer_id},{self.peer_host},{self.peer_port}".encode())
            piece = client_socket.recv(piece_length)

            piece_hash = all_hashes[i * hash_length:(i + 1) * hash_length]
            if hashlib.sha1(piece).digest() == piece_hash:
                print(f"Received and validated piece {i} from {seeder_host}:{seeder_port}")
                validated_pieces[i] = piece
                i += 1
            else:
                print(f"Piece {i} is corrupted")
                continue

            client_socket.shutdown(socket.SHUT_RDWR)
            client_socket.close()
            time.sleep(1)

        # Create directory if not exists
        directory = f"peer_{self.peer_id}"
        if not os.path.exists(directory):
            os.makedirs(directory)

        full_output_path = os.path.join(directory, filename)
        with open(full_output_path, 'wb') as file:
            for piece in validated_pieces:
                if piece is not None:
                    file.write(piece)
        print(f"File has been successfully created: {filename}")
        print("Download completed and connection closed.")
        self.notify_tracker_downloading(file_name = torrent_filename.rsplit('.torrent', 1)[0], flag = "end")
    
    def scrape_peers(self, filename):
        """Gửi yêu cầu scrape tới tracker và nhận thông tin seeders và leechers."""
        
        url = f'http://{self.tracker_host}:{self.tracker_port}/scrape'
        # Gửi yêu cầu GET tới tracker
        response = requests.get(url, params={'filename': filename})
        
        # Kiểm tra trạng thái của phản hồi
        if response.status_code == 200:
            data = response.json()
            
            # In thông tin ra với định dạng đẹp hơn
            print(f"Scrape Results for filename: {filename}")
            
        
            seeders = data.get('seeders', [])
            leechers = data.get('leechers', [])
                
            # In ra số lượng seeders và leechers
            print(f"Seeders ({len(seeders)}):")
            if seeders:
                for seeder in seeders:
                    print(f"  - {seeder['peer_id']} ({seeder['peer_host']}:{seeder['peer_port']})")
            else:
                print("  No seeders found.")
                    
            print(f"Leechers ({len(leechers)}):")
            if leechers:
                for leecher in leechers:
                    print(f"  - {leecher['peer_id']} ({leecher['peer_host']}:{leecher['peer_port']})")
            else:
                print("  No leechers found.")
        else:
            print(f"Failed to scrape: {response.status_code}")
            
        
                
def parse_arguments():
    """ Parse command-line arguments """
    parser = argparse.ArgumentParser(description="Start a torrent-like peer node.")
    parser.add_argument('--tracker-host', type=str, default='localhost', help="IP address of the tracker (default is localhost)")
    parser.add_argument('--peer-host', type=str, default='localhost', help="IP address of the peer (default is localhost)")
    parser.add_argument('--id', type=str, help="Unique ID for this peer")
    return parser.parse_args()

def print_menu():
    
    print("\n Menu commands:")
    print("1. CONNECT SERVER")
    print("2. SHARE [filename]")
    print("3. DISCONNECT SERVER")
    print("4. SEED")
    print("5. DOWNLOAD [torrent_filename]")
    print("6. SCRAPE [filename]")
    print("7. EXIT")

    
def main(id, trackerhost, peerhost):
    peer = Peer(
        peer_id=id,
        tracker_host=trackerhost,
        peer_host=peerhost
    )
    print_menu()
    while True:
        
        command = input("Enter your command: ").strip().upper()
        
        if(command == "CONNECT SERVER"):
            peer.connect_to_tracker()
        elif(command == "DISCONNECT SERVER"):
            peer.disconnect_from_tracker()
        elif(command == "SHARE"):
            FILENAME = input("Enter your file name: ").strip().lower()
            peer.create_torrent_file(FILENAME)
            peer.upload_info_hash_to_tracker(FILENAME)
        elif command == "SEED":
            Thread(target=peer.start_seeder_server, daemon=True).start()
        elif command =="DOWNLOAD":
            torrent_filename = input("Enter your file name: ").strip()
            peer.download_torrent(torrent_filename)
        elif command =="SCRAPE":
            filename = input("Enter your file name: ").strip()
            peer.scrape_peers(filename)
        # elif command == "download":
        #     TORRENT_FILE = input("Enter torrent file name: ")
        #     Thread(target=download_torrent, args=(TORRENT_FILE, CLIENT_IP, CLIENT_ID), daemon=True).start()
        # elif command == "create torrent":
        #     FILENAME = input("Enter the filename to create torrent file: ")
        #     create_torrent_file(SERVER_HOST, SERVER_PORT, FILENAME, CLIENT_ID)
        # elif command == "seeder":
        #     # Start seeder server in a separate thread
        #     Thread(target=start_seeder_server, args=(CLIENT_IP, CLIENT_PORT), daemon=True).start()
        elif(command == "MENU"):
            print_menu()
        elif(command == "EXIT"):
            break
        
        
    
if __name__ == "__main__":
    args = parse_arguments()
    main(
        id = args.id,
        trackerhost = args.tracker_host,
        peerhost = args.peer_host   
    )
