from flask import Flask, request, jsonify
import argparse
from threading import Lock
import hashlib
import os
from bencodepy import decode as bdecode
import json

app = Flask(__name__)

# Dữ liệu tracker
peers = {}
info_hashes = {}  # Thông tin về các torrent (info_hash -> metadata)
lock = Lock()

MAX_PEERS = 10

@app.route('/connect', methods=['POST'])
def peer_connect():
    """ Đăng ký peer mới """
    with lock:
        data = request.json
        peer_id = data.get('peer_id')
        peer_host = data.get('peer_host')
        peer_port = data.get('peer_port')

        if not peer_id or not peer_host or not peer_port:
            return jsonify({'status': 'fail', 'message': 'Invalid peer data'}), 400

        # Kiểm tra xem peer đã tồn tại chưa
        if peer_id in peers:
            return jsonify({'status': 'error', 'message': 'Peer already connected'}), 400

        # Đăng ký peer
        peers[peer_id] = (peer_host, peer_port)
        print(f"Peer {peer_id} registered: {peer_host}:{peer_port}")

        return jsonify({'status': 'success', 'message': f"Peer {peer_id} registered successfully"}), 200

@app.route('/peer_list', methods=['GET'])
def get_peer_list():
    """ Lấy danh sách các peer đang kết nối """
    with lock:
        info_hash = request.json
        info_hash = info_hash['info_hash']
        if info_hash in info_hashes:
            peer_info = [peer for peer in info_hashes[info_hash]['peers']]
            return jsonify({'status': 'success', 'message': 'Peer data retrieved', 'peers': peer_info}), 200
        return jsonify({'status': 'error', 'message': 'Torrent not found'}), 404

@app.route('/disconnect', methods=['POST'])
def peer_disconnect():
    """ Ngắt kết nối peer """
    with lock:
        data = request.json
        peer_id = data.get('peer_id')
        peer_host = data.get('peer_host')
        peer_port = data.get('peer_port')

        # Xác thực peer
        if peer_id in peers:
            host, port = peers[peer_id]
            if host == peer_host and port == peer_port:
                del peers[peer_id]  # Xóa peer khỏi danh sách
                for torrent in info_hashes:
                    # Remove all matching peers for this torrent
                    info_hashes[torrent]['peers'] = [
                        peer_info for peer_info in info_hashes[torrent]['peers']
                        if not (peer_info['host'] == peer_host and peer_info['port'] == peer_port)
                    ]
                            
                print(f"Peer {peer_id} disconnected: {peer_host}:{peer_port}")
                
                return jsonify({'status': 'success', 'message': 'Peer disconnected successfully'}), 200
            else:
                return jsonify({'status': 'error', 'message': 'Peer information mismatch'}), 400

        return jsonify({'status': 'error', 'message': 'Peer not found'}), 404

@app.route('/info_hash', methods=['POST'])
def upload_info_hash():
    """ Nhận và lưu thông tin torrent từ peer """
    with lock:
        data = request.json

        peer_id = data.get('peer_id')
        peer_host = data.get('peer_host')
        peer_port = data.get('peer_port')
        filename = data.get('filename')
        info_hash = data.get('info_hash')

        # Xác thực dữ liệu
        if not peer_id or not peer_host or not peer_port or not filename or not info_hash:
            return jsonify({'status': 'fail', 'message': 'Invalid data'}), 400

        # Kiểm tra info_hash có tồn tại hay chưa
        if info_hash not in info_hashes:
            # Thêm info_hash mới vào tracker
            info_hashes[info_hash] = {
                'filename': filename,
                'peers': [],
                'seeders': [],
                'leechers': []
            }

        # Thêm peer vào danh sách chia sẻ info_hash
        info_hashes[info_hash]['peers'].append({
            'peer_id': peer_id,
            'peer_host': peer_host,
            'peer_port': peer_port
        })

        print(f"Received info_hash {info_hash} for file {filename} from peer {peer_id}")
        return jsonify({'status': 'success', 'message': 'Torrent info uploaded successfully'}), 200

@app.route('/torrent_info', methods=['GET'])
def get_torrent_info():
    """ Lấy thông tin torrent từ info_hash """
    with lock:
        info_hash = request.args.get('info_hash')
        if not info_hash:
            return jsonify({'status': 'fail', 'message': 'info_hash is required'}), 400

        if info_hash not in info_hashes:
            return jsonify({'status': 'fail', 'message': 'info_hash not found'}), 404

        return jsonify(info_hashes[info_hash]), 200

@app.route('/seeding', methods=['POST'])
def seeding():
    data = request.json
    filename = data.get('filename')
    peer_host = data.get('peer_host')
    peer_port = data.get('peer_port')
    peer_id = data.get('peer_id')
    flag = data.get('flag')

    if not filename or not peer_host or not peer_port or not peer_id or not flag:
        return jsonify({"status": "fail", "message": "Missing required parameters"}), 400
    
    for info_hash, details in info_hashes.items():
        if details.get('filename') == filename:
            if flag == 'start':
                existing_seeder = next((seeder for seeder in info_hashes[info_hash]['seeders']
                                        if seeder['peer_id'] == peer_id and seeder['peer_host'] == peer_host and seeder['peer_port'] == peer_port), None)
                print(existing_seeder)
                if not existing_seeder:
                    info_hashes[info_hash]['seeders'].append({
                        'peer_id': peer_id,
                        'peer_host': peer_host,
                        'peer_port': peer_port
                    })
                return jsonify({"status": "success", "message": f"Peer {peer_id} - {peer_host}:{peer_port} is seeding {filename}"})    
                
            elif flag == 'end':
                info_hashes[info_hash]['seeders'] = [
                    seeder for seeder in info_hashes[info_hash]['seeders']
                    if not (
                        seeder['peer_id'] == peer_id and
                        seeder['peer_host'] == peer_host and
                        seeder['peer_port'] == peer_port
                    )
                ]
                print(f"Peer {peer_id} - {peer_host}:{peer_port} stop seeding.")
                return jsonify({"status": "success", "message": f"Peer {peer_id} - {peer_host}:{peer_port} stop seeding {filename}"})


@app.route('/leeching', methods=['POST'])
def leeching():
    data = request.json
    info_hash = data.get('info_hash')
    filename = data.get('filename')
    peer_host = data.get('peer_host')
    peer_port = data.get('peer_port')
    peer_id = data.get('peer_id')
    flag = data.get('flag')

    if not filename or not peer_host or not peer_port or not peer_id or not flag:
        return jsonify({"status": "fail", "message": "Missing required parameters"}), 400
    
    for info_hash, details in info_hashes.items():
        if details.get('filename') == filename:
            if flag == 'start':
                existing_leecher = next((leecher for leecher in info_hashes[info_hash]['leechers']
                                         if leecher['peer_id'] == peer_id and leecher['peer_host'] == peer_host and leecher['peer_port'] == peer_port), None)
                
                if not existing_leecher:
                    info_hashes[info_hash]['leechers'].append({
                        'peer_id': peer_id,
                        'peer_host': peer_host,
                        'peer_port': peer_port
                    })
                return jsonify({"status": "success", "message": f"Peer {peer_id} - {peer_host}:{peer_port} is downloading {filename}"})
                
            elif flag == 'end':
                info_hashes[info_hash]['leechers'] = [
                    leecher for leecher in info_hashes[info_hash]['leechers']
                    if not (
                        leecher['peer_id'] == peer_id and
                        leecher['peer_host'] == peer_host and
                        leecher['peer_port'] == peer_port
                    )
                ]
                print(f"Peer {peer_id} - {peer_host}:{peer_port} stop downloading.")
                return jsonify({"status": "success", "message": f"Peer {peer_id} - {peer_host}:{peer_port} stop downloading {filename}"})


@app.route('/scrape', methods=['GET'])
def scrape():
    """ Thực hiện scrape để lấy thông tin các peer """
    with lock:
        filename = request.args.get('filename')
        if not filename:
            return jsonify({'status': 'fail', 'message': 'filename is required'}), 400
                
        result = {}
    
        for info_hash, details in info_hashes.items():
            if details.get('filename') == filename:
                result = {
                    "seeders": info_hashes[info_hash]['seeders'], 
                    "leechers": info_hashes[info_hash]['leechers']
                }
                break
            else : result[filename] = {'status': 'fail', 'message': 'filename not found'}
        
        return jsonify(result), 200


def parse_arguments():
    parser = argparse.ArgumentParser(description="Start the tracker.")
    parser.add_argument('--host', type=str, default='localhost', help="IP address of the tracker (default is localhost)")
    parser.add_argument('--port', type=int, default=8000, help="Port number for the tracker (default is 8000)")
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()
    app.run(host=args.host, port=8000)
