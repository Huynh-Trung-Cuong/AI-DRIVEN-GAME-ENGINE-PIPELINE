from ursina import *
from dsa import StateGraph, check_minkowski_collision, check_minkowski_ccd, FrameActionHeap
import math

# ==========================================
# KHỞI TẠO HÀNG ĐỢI ƯU TIÊN SỰ KIỆN (GLOBAL HEAP)
# ==========================================
action_queue = FrameActionHeap()

# --- UTILS ---
def distance_xz(p1, p2):
    """Tính khoảng cách Euclid trên mặt phẳng XZ (bỏ qua cao độ Y)."""
    return math.sqrt((p1.x - p2.x)**2 + (p1.z - p2.z)**2)

def check_world_collision(old_pos, new_pos, scale, ignore_entities):
    """
    Kiểm tra va chạm liên tục (CCD) với địa hình và các thực thể khác.
    
    Hàm này duyệt qua tất cả thực thể trong scene để tìm các đối tượng có Collider, 
    ngoại trừ các đối tượng nằm trong danh sách ignore_entities.
    """
    for e in scene.entities:
        if e.collider and e not in ignore_entities and not getattr(e, 'destroyed', False):
            if getattr(e, 'is_ground', False):
                continue
            
            if getattr(e, 'is_terrain', False) or isinstance(e, (Player1, Player2)):
                if check_minkowski_ccd(old_pos, new_pos, scale, e.position, e.position, e.scale):
                    return True
    return False

# =====================================================================
# PLAYER 1: AZAZEL - THE HELLFIRE INQUISITOR
# =====================================================================
class Player1(Entity):
    """
    Lớp quản lý nhân vật Player 1 (Azazel).
    
    Kế thừa từ Entity của Ursina Engine, lớp này chịu trách nhiệm:
    1. Quản lý trạng thái thông qua StateGraph (FSM).
    2. Xử lý các kỹ năng đặc trưng dựa trên HP (Tiêu tốn máu để dùng chiêu).
    3. Tương tác với hệ thống va chạm và mục tiêu đối thủ.
    """
    def __init__(self, start_pos, controls, **kwargs):
        super().__init__(
            model='cube', 
            collider='box', 
            color=color.violet, 
            position=start_pos, 
            scale=(1.3, 1.3, 1.3),
            **kwargs
        )
        
        self.hp = 100
        self.max_hp = 100
        self.controls = controls
        self.enemy_target = None
        self.description = """
<violet>AZAZEL - THE HELLFIRE INQUISITOR</violet>
- Passive: Demonic Exhaustion. Tiêu tốn % máu để dùng chiêu. Mạnh hơn khi thấp HP.
- Skill 1 (2): Soul-Binding Pyre. Vùng lửa xích. Địch lướt ra bị xích kéo lại + Choáng 0.75s.
- Skill 2 (3): Infernal Dash & Brand. Lướt xuyên địch, hồi chiêu nếu qua Pyre. Tái kích hoạt: Hất tung.
"""
        self.cooldown1 = 0.0
        self.cooldown2 = 0.0
        self.cd1_max = 12.0
        self.cd2_max = 9.0
        
        self.sm = StateGraph("IDLE")
        self.setup_state_machine()
        
        self.base_speed = 5
        self.old_pos = self.position
        self.direction = Vec3(0, 0, 1)
        self.hitstun_timer = 0
        self.inquisition_circle = None
        self.mark_of_cain_timer = 0
        self.can_recast_skill2 = False
        self.cinder_stacks = 0

    def setup_state_machine(self):
        """
        Thiết lập cấu trúc đồ thị trạng thái cho Azazel.
        
        Sử dụng Guard Conditions (lambda) để kiểm soát việc chuyển trạng thái 
        dựa trên thời gian hồi chiêu (Cooldown).
        """
        states = ["IDLE", "MOVE", "ATTACK", "SKILL1", "SKILL2", "HITSTUN", "DASH"]
        for s in states:
            self.sm.add_state(s)
            
        self.sm.add_edge("IDLE", "MOVE")
        self.sm.add_edge("MOVE", "IDLE")
        
        for base_state in ["IDLE", "MOVE"]:
            self.sm.add_edge(base_state, "ATTACK")
            self.sm.add_edge(base_state, "SKILL1", lambda: self.cooldown1 <= 0)
            self.sm.add_edge(base_state, "SKILL2", lambda: self.cooldown2 <= 0)
        
        for s in states:
            self.sm.add_edge(s, "HITSTUN")
        self.sm.add_edge("HITSTUN", "IDLE")
        self.sm.add_edge("SKILL2", "DASH")
        self.sm.add_edge("DASH", "IDLE")
        self.sm.add_edge("ATTACK", "IDLE")
        self.sm.add_edge("SKILL1", "IDLE")
        self.sm.add_edge("SKILL2", "IDLE")

    def take_damage(self, amount, type='normal'):
        """Xử lý nhận sát thương và hiệu ứng nháy màu."""
        self.hp -= amount
        self.hp = max(0, self.hp)
        self.flash_color = color.white
        invoke(setattr, self, 'flash_color', self.color, delay=0.1)

    def update(self):
        """Cập nhật logic theo từng frame (Cooldown, Hitstun, Skill mechanics)."""
        self.old_pos = Vec3(self.position)
        
        if self.cooldown1 > 0: self.cooldown1 -= time.dt
        if self.cooldown2 > 0: self.cooldown2 -= time.dt
        if self.mark_of_cain_timer > 0: self.mark_of_cain_timer -= time.dt

        if self.hitstun_timer > 0:
            self.hitstun_timer -= time.dt
            if self.hitstun_timer <= 0:
                self.end_hitstun()

        if self.inquisition_circle and not getattr(self.inquisition_circle, 'destroyed', False):
            dist = distance_xz(self.enemy_target.position, self.inquisition_circle.position)
            if dist < 5:
                self.cinder_stacks = min(10, self.cinder_stacks + time.dt * 4)
            
            if dist > 5.2 and dist < 10 and self.enemy_target.sm.current_state in ["MOVE", "DASH", "CHARGE"]:
                self.enemy_target.position = lerp(self.enemy_target.position, self.inquisition_circle.position, time.dt * 8)
                action_queue.push_action(1, self.enemy_target.apply_hitstun, 0.75)
                line = Entity(model='cube', color=color.violet, scale=(0.1, 0.1, dist), position=(self.enemy_target.position + self.inquisition_circle.position)/2)
                line.look_at(self.inquisition_circle.position)
                destroy(line, delay=0.1)

    def input(self, key):
        """Xử lý input phím kỹ năng."""
        if key == self.controls['skill1']: self.execute_skill1()
        if key == self.controls['skill2']: self.execute_skill2()

    def execute_skill1(self):
        """Thi triển Skill 1: Soul-Binding Pyre (Vùng lửa xích)."""
        if self.sm.request_transition("SKILL1"):
            cost = self.hp * 0.05
            self.hp -= cost
            self.cooldown1 = self.cd1_max
            self.cinder_stacks = 0
            self.inquisition_circle = Entity(model='cylinder', color=color.rgba(138, 43, 226, 80), scale=(10, 0.1, 10), position=self.position)
            invoke(self.explode_pyre, delay=4.0)
            invoke(self.reset_to_idle, delay=0.5)

    def explode_pyre(self):
        """Kích hoạt vụ nổ của kỹ năng 1."""
        if not self.inquisition_circle or getattr(self.inquisition_circle, 'destroyed', False): return
        exp = Entity(model='cube', color=color.violet, scale=0.1, position=self.inquisition_circle.position)
        exp.animate_scale(10, duration=0.3)
        destroy(exp, delay=0.3)
        if distance_xz(self.enemy_target.position, self.inquisition_circle.position) < 5:
            passive_mult = 1.0 + (1.0 - (self.hp / self.max_hp)) * 0.5
            base_dmg = 15 * passive_mult
            multiplier = 1 + (self.cinder_stacks / 10)
            action_queue.push_action(2, self.enemy_target.take_damage, base_dmg * multiplier)
        destroy(self.inquisition_circle)
        self.inquisition_circle = None

    def execute_skill2(self):
        """Thi triển Skill 2: Infernal Dash & Brand (Lướt xuyên và Đánh dấu)."""
        if self.can_recast_skill2:
            self.recast_skill2()
            return
        if self.sm.request_transition("SKILL2"):
            cost = self.hp * 0.03
            self.hp -= cost
            self.cooldown2 = self.cd2_max
            self.sm.request_transition("DASH")
            start_pos = Vec3(self.position)
            target_pos = self.position + self.forward * 9
            if check_world_collision(self.position, target_pos, self.scale, [self]):
                target_pos = self.position + self.forward * 2
            if self.inquisition_circle:
                mid_point = (start_pos + target_pos) / 2
                if distance_xz(mid_point, self.inquisition_circle.position) < 5:
                    self.cooldown2 = 0
            self.animate_position(target_pos, duration=0.2, curve=curve.linear)
            if distance(target_pos, self.enemy_target.position) < 3:
                self.mark_of_cain_timer = 3.0
            self.can_recast_skill2 = True
            invoke(setattr, self, 'can_recast_skill2', False, delay=1.5)
            invoke(self.reset_to_idle, delay=0.2)

    def recast_skill2(self):
        """Tái kích hoạt Skill 2: Trừng phạt dấu ấn."""
        self.can_recast_skill2 = False
        if self.mark_of_cain_timer > 0:
            is_chained = self.inquisition_circle and distance_xz(self.enemy_target.position, self.inquisition_circle.position) < 5
            passive_mult = 1.0 + (1.0 - (self.hp / self.max_hp)) * 0.5
            dmg = 20 * passive_mult
            if is_chained:
                action_queue.push_action(2, self.enemy_target.take_damage, dmg, type='true')
                action_queue.push_action(1, self.enemy_target.apply_hitstun, 1.25)
            else:
                action_queue.push_action(2, self.enemy_target.take_damage, dmg)
            self.mark_of_cain_timer = 0
            sweep = Entity(model='cube', color=color.violet, scale=(4, 0.5, 1), position=self.position + self.forward * 1.5)
            sweep.animate_scale((6, 0.5, 2), duration=0.2)
            destroy(sweep, delay=0.2)

    def reset_to_idle(self):
        """Đưa nhân vật về trạng thái IDLE an toàn."""
        if self.sm.current_state not in ["HITSTUN"]:
            self.sm.request_transition("IDLE")

    def apply_hitstun(self, duration):
        """Áp dụng trạng thái choáng."""
        if self.sm.request_transition("HITSTUN"):
            self.color = color.white
            self.hitstun_timer = duration
            
    def end_hitstun(self):
        """Kết thúc choáng."""
        self.color = color.violet
        self.sm.request_transition("IDLE")

# =====================================================================
# PLAYER 2: DR. VERMUND - THE PLAGUE VIVISECTOR
# =====================================================================
class Player2(Entity):
    """
    Lớp quản lý nhân vật Player 2 (Dr. Vermund).
    
    Đặc trưng: Các hiệu ứng làm chậm (Slow) và gây sát thương theo thời gian (DOT).
    Sử dụng StateGraph để quản lý Windup (vận chiêu) cho các đòn đánh mạnh.
    """
    def __init__(self, start_pos, controls, **kwargs):
        super().__init__(
            model='cube', 
            collider='box', 
            color=color.lime, 
            position=start_pos, 
            scale=(1.4, 1.4, 1.4),
            **kwargs
        )
        self.hp = 100
        self.max_hp = 100
        self.controls = controls
        self.enemy_target = None
        self.description = """
<lime>DR. VERMUND - THE PLAGUE VIVISECTOR</lime>
- Passive: Blood Siphon. "Đánh cắp" tốc độ kẻ địch. Càng chậm địch, ta càng nhanh.
- Skill 1 (N): Crippling Injection. Phóng thuốc tê. Địch bị làm chậm + tăng thời gian ra chiêu.
- Skill 2 (M): Vivisection Cleave. Nhát chém tàn bạo. Dame tăng theo tốc độ địch đã mất. Grounded.
"""
        self.cooldown1 = 0.0
        self.cooldown2 = 0.0
        self.cd1_max = 10.0
        self.cd2_max = 8.0
        
        self.sm = StateGraph("IDLE")
        self.setup_state_machine()
        
        self.base_speed = 3.5
        self.direction = Vec3(0, 0, 1)
        self.hitstun_timer = 0
        self.injection_timer = 0
        self.is_winding_up = False
        self.grounded_timer = 0
        self.hemorrhage_timer = 0
        self.last_enemy_pos = Vec3(0,0,0)

    def setup_state_machine(self):
        """Thiết lập đồ thị trạng thái cho Dr. Vermund."""
        states = ["IDLE", "MOVE", "ATTACK", "SKILL1", "SKILL2", "HITSTUN", "WINDUP"]
        for s in states: self.sm.add_state(s)
        self.sm.add_edge("IDLE", "MOVE")
        self.sm.add_edge("MOVE", "IDLE")
        for base_state in ["IDLE", "MOVE"]:
            self.sm.add_edge(base_state, "ATTACK")
            self.sm.add_edge(base_state, "SKILL1", lambda: self.cooldown1 <= 0)
            self.sm.add_edge(base_state, "SKILL2", lambda: self.cooldown2 <= 0)
        for s in states: self.sm.add_edge(s, "HITSTUN")
        self.sm.add_edge("HITSTUN", "IDLE")
        self.sm.add_edge("SKILL2", "WINDUP")
        self.sm.add_edge("WINDUP", "IDLE")
        self.sm.add_edge("ATTACK", "IDLE")
        self.sm.add_edge("SKILL1", "IDLE")
        self.sm.add_edge("SKILL2", "IDLE")

    def take_damage(self, amount, type='normal'):
        """Xử lý nhận sát thương, có cơ chế giảm sát thương khi đang vận chiêu."""
        if self.is_winding_up: amount *= 0.7
        self.hp -= amount
        self.hp = max(0, self.hp)
        self.flash_color = color.white
        invoke(setattr, self, 'flash_color', self.color, delay=0.1)

    def update(self):
        """Cập nhật logic theo frame (Passive hút tốc độ, DOT sát thương)."""
        self.old_pos = Vec3(self.position)
        if self.cooldown1 > 0: self.cooldown1 -= time.dt
        if self.cooldown2 > 0: self.cooldown2 -= time.dt
        if self.injection_timer > 0: self.injection_timer -= time.dt
        if self.grounded_timer > 0: self.grounded_timer -= time.dt
        if self.hemorrhage_timer > 0: self.hemorrhage_timer -= time.dt

        if self.hitstun_timer > 0:
            self.hitstun_timer -= time.dt
            if self.hitstun_timer <= 0:
                self.end_hitstun()
            
        # Cơ chế Passive: Blood Siphon
        enemy_current_speed = getattr(self.enemy_target, 'base_speed', 5.0)
        enemy_slow_ratio = max(0, 1.0 - (enemy_current_speed / 5.0))
        self.base_speed = 3.5 + (enemy_slow_ratio * 4.0)

        # Gây sát thương theo di chuyển (Hemorrhage)
        if self.hemorrhage_timer > 0:
            if distance_xz(self.enemy_target.position, self.last_enemy_pos) > 0.05:
                action_queue.push_action(2, self.enemy_target.take_damage, 10 * time.dt)
        self.last_enemy_pos = Vec3(self.enemy_target.position)

        # Hiệu ứng Grounded
        if self.grounded_timer > 0:
            self.enemy_target.cooldown2 = max(self.enemy_target.cooldown2, 0.5)

    def input(self, key):
        """Xử lý phím bấm kỹ năng."""
        if key == self.controls['skill1']: self.execute_skill1()
        if key == self.controls['skill2']: self.execute_skill2()

    def execute_skill1(self):
        """Thi triển Skill 1: Phóng thuốc tê (Projectile)."""
        if self.sm.request_transition("SKILL1"):
            self.cooldown1 = self.cd1_max
            bullet = Entity(model='cube', color=color.lime, scale=0.4, position=self.position + self.forward * 1.5)
            bullet.animate_position(bullet.position + self.forward * 15, duration=0.6)
            destroy(bullet, delay=0.6)
            for i in range(1, 7):
                invoke(self.check_injection, bullet, delay=i*0.1)
            invoke(self.reset_to_idle, delay=0.3)

    def check_injection(self, bullet):
        """Kiểm tra va chạm của kim tiêm với kẻ địch."""
        if not bullet or getattr(bullet, 'destroyed', False): return
        if distance(bullet.position, self.enemy_target.position) < 2.5:
            orig_speed = 5.0
            self.enemy_target.base_speed = orig_speed * 0.6
            self.injection_timer = 2.5
            invoke(setattr, self.enemy_target, 'base_speed', orig_speed * 0.2, delay=1.25)
            invoke(setattr, self.enemy_target, 'base_speed', orig_speed, delay=2.5)
            self.hemorrhage_timer = 4.0
            destroy(bullet)

    def execute_skill2(self):
        """Thi triển Skill 2: Nhát chém tàn bạo (Cần vận chiêu)."""
        if self.sm.request_transition("SKILL2"):
            self.cooldown2 = self.cd2_max
            self.is_winding_up = True
            self.sm.request_transition("WINDUP")
            self.color = color.white
            invoke(self.perform_cleave, delay=0.75)

    def perform_cleave(self):
        """Thực hiện nhát chém sau khi vận chiêu xong."""
        if self.sm.current_state == "HITSTUN":
            self.is_winding_up = False
            return
        self.is_winding_up = False
        self.color = color.lime
        enemy_lost_speed_ratio = max(0, 1.0 - (self.enemy_target.base_speed / 5.0))
        base_dmg = 20
        bonus_dmg_mult = 1.0 + (enemy_lost_speed_ratio * 2.0)
        if distance(self.position, self.enemy_target.position) < 4.5:
            action_queue.push_action(2, self.enemy_target.take_damage, base_dmg * bonus_dmg_mult)
            self.grounded_timer = 3.0
            self.hp = min(self.max_hp, self.hp + 15)
            zone = Entity(model='cube', color=color.rgba(0, 255, 0, 40), scale=(6, 0.1, 6), position=self.enemy_target.position)
            destroy(zone, delay=3.0)
        cleave = Entity(model='cube', color=color.red, scale=(5, 0.2, 1), position=self.position + self.forward * 2)
        cleave.animate_scale((8, 0.2, 3), duration=0.2)
        destroy(cleave, delay=0.2)
        self.sm.request_transition("IDLE")

    def reset_to_idle(self):
        """Đưa về IDLE an toàn."""
        if self.sm.current_state not in ["HITSTUN", "WINDUP"]:
            self.sm.request_transition("IDLE")

    def apply_hitstun(self, duration):
        """Áp dụng choáng."""
        if self.sm.request_transition("HITSTUN"):
            self.color = color.black
            self.hitstun_timer = duration
            
    def end_hitstun(self):
        """Kết thúc choáng."""
        self.color = color.lime
        self.sm.request_transition("IDLE")
