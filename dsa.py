import heapq

# ==========================================
# 1. GIẢI THUẬT MINKOWSKI & SWEPT AABB (CHỐNG XUYÊN THẤU)
# ==========================================
def check_minkowski_collision(pos_a, size_a, pos_b, size_b):
    """
    Kiểm tra va chạm giữa hai khối AABB (Axis-Aligned Bounding Box) bằng Minkowski Difference.
    
    Giải thuật này tính toán khoảng cách tương đối giữa hai tâm vật thể và so sánh 
    với tổng bán kính (extents) của chúng trên cả 3 trục X, Y, Z.
    
    Args:
        pos_a (Vec3): Vị trí tâm vật thể A.
        size_a (Vec3): Kích thước vật thể A.
        pos_b (Vec3): Vị trí tâm vật thể B.
        size_b (Vec3): Kích thước vật thể B.
        
    Returns:
        bool: True nếu có va chạm xảy ra.
    """
    extents_a = (size_a[0]/2, size_a[1]/2, size_a[2]/2)
    extents_b = (size_b[0]/2, size_b[1]/2, size_b[2]/2)
    
    diff_x = abs(pos_a[0] - pos_b[0])
    diff_y = abs(pos_a[1] - pos_b[1])
    diff_z = abs(pos_a[2] - pos_b[2])
    
    sum_extents_x = extents_a[0] + extents_b[0]
    sum_extents_y = extents_a[1] + extents_b[1]
    sum_extents_z = extents_a[2] + extents_b[2]
    
    return (diff_x <= sum_extents_x) and (diff_y <= sum_extents_y) and (diff_z <= sum_extents_z)

def check_minkowski_ccd(pos_a_old, pos_a_new, size_a, pos_b_old, pos_b_new, size_b):
    """
    Thuật toán Continuous Collision Detection (CCD) - Kiểm tra va chạm liên tục.
    
    Vấn đề: Ở tốc độ cao, vật thể có thể đi xuyên qua nhau giữa 2 khung hình (Tunneling).
    Giải pháp: Thuật toán Swept AABB tạo ra một "khối quét" bao trùm toàn bộ quỹ đạo di chuyển 
    từ vị trí cũ đến vị trí mới, sau đó mới thực hiện kiểm tra va chạm trên khối quét này.
    
    Args:
        pos_a_old (Vec3): Vị trí của vật thể A ở frame trước.
        pos_a_new (Vec3): Vị trí của vật thể A ở frame hiện tại.
        size_a (Vec3): Kích thước vật thể A.
        pos_b_old (Vec3): Vị trí của vật thể B ở frame trước.
        pos_b_new (Vec3): Vị trí của vật thể B ở frame hiện tại.
        size_b (Vec3): Kích thước vật thể B.
        
    Returns:
        bool: True nếu quỹ đạo di chuyển của hai vật thể giao nhau.
    """
    # Bước 1: Tính toán tâm của quỹ đạo (Trung điểm của điểm cũ và mới)
    swept_center_a = (
        (pos_a_old[0] + pos_a_new[0]) / 2,
        (pos_a_old[1] + pos_a_new[1]) / 2,
        (pos_a_old[2] + pos_a_new[2]) / 2
    )
    swept_center_b = (
        (pos_b_old[0] + pos_b_new[0]) / 2,
        (pos_b_old[1] + pos_b_new[1]) / 2,
        (pos_b_old[2] + pos_b_new[2]) / 2
    )
    
    # Bước 2: Giãn nở Hitbox để bao trùm toàn bộ quãng đường di chuyển (Swept Volume)
    swept_size_a = (
        size_a[0] + abs(pos_a_new[0] - pos_a_old[0]),
        size_a[1] + abs(pos_a_new[1] - pos_a_old[1]),
        size_a[2] + abs(pos_a_new[2] - pos_a_old[2])
    )
    swept_size_b = (
        size_b[0] + abs(pos_b_new[0] - pos_b_old[0]),
        size_b[1] + abs(pos_b_new[1] - pos_b_old[1]),
        size_b[2] + abs(pos_b_new[2] - pos_b_old[2])
    )
    
    # Bước 3: Đưa 2 khối Swept Volume này vào thuật toán Minkowski tĩnh để test
    return check_minkowski_collision(swept_center_a, swept_size_a, swept_center_b, swept_size_b)


# ==========================================
# 2. ĐỒ THỊ TRẠNG THÁI CÓ ĐIỀU KIỆN (GUARDED DIRECTED GRAPH)
# ==========================================
class StateGraph:
    """
    Cấu trúc dữ liệu Đồ thị có hướng (Directed Graph) ứng dụng cho Máy trạng thái (FSM).
    
    Mỗi nút đại diện cho một trạng thái nhân vật (Idle, Attack, ...).
    Mỗi cạnh nối đại diện cho một khả năng chuyển dịch trạng thái, đi kèm với một hàm 
    điều kiện (Guard Condition) để kiểm soát logic (ví dụ: kiểm tra Cooldown).
    """
    def __init__(self, initial_state="IDLE"):
        self.adj_list = {}
        self.current_state = initial_state
        self.add_state(initial_state)

    def add_state(self, state):
        """Thêm một nút trạng thái mới vào đồ thị."""
        if state not in self.adj_list:
            self.adj_list[state] = []

    def add_edge(self, from_state, to_state, condition_func=None):
        """
        Thêm một cạnh nối (khả năng chuyển trạng thái) giữa 2 nút.
        
        Args:
            from_state: Trạng thái bắt đầu.
            to_state: Trạng thái đích.
            condition_func: Hàm lambda trả về True/False để quyết định có cho phép chuyển hay không.
        """
        self.add_state(from_state)
        self.add_state(to_state)
        
        self.adj_list[from_state].append({
            'to': to_state,
            'condition': condition_func
        })

    def request_transition(self, new_state, *args, **kwargs):
        """
        Yêu cầu thực hiện việc chuyển dịch trạng thái.
        
        Hệ thống sẽ duyệt danh sách kề để tìm cạnh nối. Nếu có cạnh nối, nó sẽ 
        kiểm tra Guard Condition. Nếu thỏa mãn, trạng thái hiện tại sẽ được cập nhật.
        """
        valid_edges = self.adj_list.get(self.current_state, [])
        for edge in valid_edges:
            if edge['to'] == new_state:
                # Kiểm tra điều kiện bảo vệ (Guard Check)
                if edge['condition'] is None or edge['condition'](*args, **kwargs):
                    self.current_state = new_state
                    return True
                else:
                    return False
        return False

# CÁCH SỬ DỤNG STATE GRAPH VỚI ĐIỀU KIỆN:
# Khởi tạo:
# self.state_machine = StateGraph("IDLE")
#
# Thêm cạnh với điều kiện dùng Lambda (chỉ được chém khi cooldown <= 0 và có mana):
# self.state_machine.add_edge("IDLE", "WINDUP", condition_func=lambda: self.cooldown1 <= 0 and self.mana >= 20)
#
# Khi bấm phím tung chiêu:
# if self.state_machine.request_transition("WINDUP"):
#     self.cooldown1 = 5.0 # Set lại hồi chiêu
#     self.mana -= 20
#     thuc_hien_chieu()


# ==========================================
# 3. HÀNG ĐỢI ƯU TIÊN SỰ KIỆN (MIN-HEAP)
# ==========================================
class FrameActionHeap:
    """
    Hệ thống hàng đợi ưu tiên (Priority Queue) dựa trên cấu trúc Min-Heap.
    
    Lớp này cho phép đăng ký các hàm (actions) sẽ được thực thi vào cuối khung hình 
    theo một thứ tự ưu tiên xác định. Điều này hữu ích để tách biệt logic tính toán 
    và logic thực thi (ví dụ: tính sát thương xong rồi mới trừ máu).
    """
    def __init__(self):
        """Khởi tạo hàng đợi trống và bộ đếm thứ tự để đảm bảo tính ổn định (Stable Sort)."""
        self.heap = []
        self.action_counter = 0

    def push_action(self, priority, func, *args, **kwargs):
        """
        Thêm một hành động vào hàng đợi.
        
        Args:
            priority (int): Giá trị ưu tiên (nhỏ hơn sẽ được thực thi trước).
            func (callable): Hàm sẽ được gọi.
            *args: Các tham số vị trí truyền vào hàm.
            **kwargs: Các tham số từ khóa truyền vào hàm.
        """
        heapq.heappush(self.heap, (priority, self.action_counter, func, args, kwargs))
        self.action_counter += 1

    def process_all_actions(self):
        """Lấy tất cả hành động ra khỏi heap theo thứ tự ưu tiên và thực thi chúng."""
        while self.heap:
            priority, count, func, args, kwargs = heapq.heappop(self.heap)
            func(*args, **kwargs)
# CÁCH SỬ DỤNG HEAP:
# Khởi tạo ở base.py:
# action_queue = FrameActionHeap()
#
# Trong game loop, khi cần đăng ký sự kiện:
# action_queue.push_action(1, check_collision_function)  # Ưu tiên cao nhất, chạy trước
# action_queue.push_action(3, update_ui_function)        # Ưu tiên thấp, chạy sau
#
# Ở cuối hàm update() của base.py:
# action_queue.process_all_actions()