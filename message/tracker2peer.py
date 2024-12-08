def handle_register(message, addr, peers, sock):
    """
    Xử lý thông điệp REGISTER từ peer.
    message: Thông điệp từ peer (dạng chuỗi).
    addr: Địa chỉ của peer gửi thông điệp.
    peers: Dictionary lưu trữ danh sách peer đã đăng ký.
    sock: Socket UDP để gửi phản hồi.
    """
    peer_id = message.split()[1]
    peers[peer_id] = addr
    print(f"Peer {peer_id} registered at {addr}")
    sock.sendto("Registration successful".encode(), addr)


def handle_peer_list(addr, peers, sock):
    """
    Xử lý yêu cầu PEER_LIST từ peer.
    addr: Địa chỉ của peer gửi yêu cầu.
    peers: Dictionary lưu trữ danh sách peer đã đăng ký.
    sock: Socket UDP để gửi danh sách.
    """
    peer_list = "\n".join([f"{peer_id} {peer_addr}" for peer_id, peer_addr in peers.items()])
    sock.sendto(peer_list.encode(), addr)
    print(f"Sent peer list to {addr}")


def process_message(message, addr, peers, sock):
    """
    Xử lý các loại thông điệp từ peer.
    message: Thông điệp từ peer.
    addr: Địa chỉ của peer gửi thông điệp.
    peers: Dictionary lưu trữ danh sách peer đã đăng ký.
    sock: Socket UDP để gửi phản hồi.
    """
    if message.startswith("REGISTER"):
        handle_register(message, addr, peers, sock)
    elif message == "PEER_LIST":
        handle_peer_list(addr, peers, sock)
    else:
        print(f"Unknown message from {addr}: {message}")
        sock.sendto("Unknown command".encode(), addr)
