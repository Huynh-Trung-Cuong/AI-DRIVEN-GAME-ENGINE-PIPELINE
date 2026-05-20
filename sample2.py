from ursina import *
from dsa import StateGraph, check_minkowski_collision, check_minkowski_ccd, FrameActionHeap
import math


action_queue = FrameActionHeap()


def _v3(value):
    if isinstance(value, Vec3):
        return Vec3(value)
    return Vec3(value[0], value[1], value[2])


def _flat(value):
    v = _v3(value)
    return Vec3(v.x, 0, v.z)


def _safe_dir(value, fallback=Vec3(0, 0, 1)):
    direction = _flat(value)
    if direction.length() <= 0.001:
        return Vec3(fallback)
    return direction.normalized()


def _perp(direction):
    direction = _safe_dir(direction)
    return Vec3(direction.z, 0, -direction.x)


def _angle_y(direction):
    direction = _safe_dir(direction)
    return math.degrees(math.atan2(direction.x, direction.z))


def _distance_xz(a, b):
    return (_flat(a) - _flat(b)).length()


def _is_alive(entity):
    return entity is not None and not getattr(entity, "destroyed", False) and getattr(entity, "hp", 0) > 0


def _entity_gone(entity):
    if entity is None or getattr(entity, "destroyed", False) or getattr(entity, "dead", False):
        return True
    try:
        return entity.is_empty()
    except Exception:
        return False


def _is_projectile(entity):
    return isinstance(entity, Entity) and getattr(entity, "is_straight_projectile", False)


def _entity_transform(entity):
    if _entity_gone(entity):
        return None, None
    try:
        return Vec3(entity.position), Vec3(entity.scale)
    except Exception:
        return None, None


def _spawn_fx(position, scale, tint, duration=0.15, rotation_y=0):
    fx = Entity(model="cube", position=Vec3(position), scale=scale, color=tint, rotation_y=rotation_y)
    fx.animate_scale(0, duration=duration)
    destroy(fx, delay=duration)
    return fx


def _find_enemy(owner):
    if _is_alive(getattr(owner, "enemy_target", None)):
        return owner.enemy_target
    for entity in scene.entities:
        if isinstance(entity, BasePlayer) and entity is not owner and _is_alive(entity):
            return entity
    return None


def check_world_collision(old_pos, new_pos, size, ignore=None):
    ignore = set(ignore or [])
    for entity in list(scene.entities):
        if entity in ignore or _entity_gone(entity):
            continue
        if getattr(entity, "is_ground", False):
            continue
        if not (getattr(entity, "is_terrain", False) or getattr(entity, "is_skill_wall", False)):
            continue
        entity_pos, entity_scale = _entity_transform(entity)
        if entity_pos is None:
            continue
        if check_minkowski_ccd(old_pos, new_pos, size, entity_pos, entity_pos, entity_scale):
            return True
    return False


def _try_move_entity(entity, target_pos, ignore=None):
    old_pos = Vec3(entity.position)
    target_pos = Vec3(target_pos)
    ignore_list = [entity] + list(ignore or [])
    if not check_world_collision(old_pos, target_pos, entity.scale, ignore_list):
        entity.position = target_pos
        return True

    x_only = Vec3(target_pos.x, old_pos.y, old_pos.z)
    z_only = Vec3(old_pos.x, old_pos.y, target_pos.z)
    moved = False
    if not check_world_collision(old_pos, x_only, entity.scale, ignore_list):
        entity.position = x_only
        old_pos = Vec3(entity.position)
        moved = True
    if not check_world_collision(old_pos, z_only, entity.scale, ignore_list):
        entity.position = z_only
        moved = True
    return moved


def _move_body_blocked(entity, delta, blocker=None):
    old_pos = Vec3(entity.position)
    target_pos = old_pos + delta
    if check_world_collision(old_pos, target_pos, entity.scale, [entity]):
        return False
    if blocker is not None and _is_alive(blocker):
        if check_minkowski_collision(target_pos, entity.scale, blocker.position, blocker.scale):
            best = Vec3(old_pos)
            for i in range(1, 13):
                probe = lerp(old_pos, target_pos, i / 12)
                if check_minkowski_collision(probe, entity.scale, blocker.position, blocker.scale):
                    break
                best = Vec3(probe)
            if best != old_pos:
                entity.position = best
                return True
            return False
    entity.position = target_pos
    return True


def _clamp_path(entity, target_pos, ignore=None, steps=12):
    start = Vec3(entity.position)
    target_pos = Vec3(target_pos)
    best = Vec3(start)
    ignore_list = [entity] + list(ignore or [])
    for i in range(1, steps + 1):
        probe = lerp(start, target_pos, i / steps)
        if check_world_collision(best, probe, entity.scale, ignore_list):
            break
        best = Vec3(probe)
    return best


def _half_circle_hit(caster, target, radius):
    if not _is_alive(target):
        return False
    offset = _flat(target.position - caster.position)
    if offset.length() > radius:
        return False
    if offset.length() <= 0.001:
        return True
    return _safe_dir(caster.locked_direction).dot(offset.normalized()) >= -0.15


def _front_rect_hit(origin, direction, target, length, width):
    if not _is_alive(target):
        return False
    direction = _safe_dir(direction)
    offset = _flat(target.position - origin)
    along = offset.dot(direction)
    side = offset.dot(_perp(direction))
    return 0 <= along <= length + target.scale.z * 0.5 and abs(side) <= width * 0.5 + target.scale.x * 0.5


class SimpleProjectile(Entity):
    def __init__(self, start_pos, direction, owner, damage=6, speed=14.0, max_range=6.0, color_tint=None):
        super().__init__(
            model="cube",
            collider="box",
            scale=(0.24, 0.24, 0.24),
            position=Vec3(start_pos),
            color=color_tint or owner.color,
        )
        self.owner = owner
        self.direction = _safe_dir(direction, owner.direction)
        self.damage = damage
        self.speed = speed
        self.max_range = max_range
        self.travelled = 0.0
        self.dead = False
        self.is_straight_projectile = True

    def destroy_self(self):
        if not self.dead:
            self.dead = True
            destroy(self)

    def update(self):
        if _entity_gone(self) or not _is_alive(self.owner):
            self.destroy_self()
            return
        old_pos = Vec3(self.position)
        delta = self.direction * self.speed * time.dt
        new_pos = old_pos + delta
        if check_world_collision(old_pos, new_pos, self.scale, [self, self.owner]):
            self.destroy_self()
            return

        enemy = _find_enemy(self.owner)
        if _is_alive(enemy) and check_minkowski_ccd(old_pos, new_pos, self.scale, enemy.position, enemy.position, enemy.scale):
            action_queue.push_action(3, enemy.take_damage, self.damage, self)
            _spawn_fx(new_pos, 0.4, self.color, 0.10)
            self.destroy_self()
            return

        self.position = new_pos
        self.travelled += delta.length()
        if self.travelled >= self.max_range:
            self.destroy_self()


class HookProjectile(Entity):
    def __init__(self, owner, direction):
        super().__init__(
            model="cube",
            collider="box",
            position=owner.position + Vec3(0, 0.2, 0) + direction * 0.6,
            scale=(0.28, 0.28, 0.6),
            rotation_y=_angle_y(direction),
            color=color.rgb(90, 80, 70),
        )
        self.owner = owner
        self.direction = _safe_dir(direction, owner.direction)
        self.speed = 12.0
        self.max_range = 4.0
        self.travelled = 0.0
        self.dead = False
        self.is_straight_projectile = True

    def destroy_self(self):
        if not self.dead:
            self.dead = True
            destroy(self)

    def update(self):
        if _entity_gone(self) or not _is_alive(self.owner):
            self.destroy_self()
            return

        enemy = _find_enemy(self.owner)
        old_pos = Vec3(self.position)
        delta = self.direction * self.speed * time.dt
        new_pos = old_pos + delta

        if check_world_collision(old_pos, new_pos, self.scale, [self, self.owner]):
            self.destroy_self()
            return

        if _is_alive(enemy) and enemy.sm.current_state == "P2_S21_HOP":
            if check_minkowski_ccd(old_pos, new_pos, self.scale, enemy.prev_position, enemy.position, enemy.scale):
                action_queue.push_action(1, self.destroy_self)
                _spawn_fx(enemy.position + Vec3(0, 0.35, 0), 0.32, color.rgb(230, 220, 170), 0.08)
                return

        if _is_alive(enemy) and check_minkowski_ccd(old_pos, new_pos, self.scale, enemy.prev_position, enemy.position, enemy.scale):
            action_queue.push_action(2, enemy.apply_status, "shackled", 2.2)
            action_queue.push_action(3, enemy.take_damage, 8, self.owner)
            action_queue.push_action(4, enemy.pull_toward, self.owner, 0.9)
            action_queue.push_action(1, self.destroy_self)
            _spawn_fx(enemy.position + Vec3(0, -0.2, 0), (0.8, 0.08, 0.8), color.rgb(207, 177, 120), 0.12)
            return

        self.position = new_pos
        self.travelled += delta.length()
        if self.travelled >= self.max_range:
            self.destroy_self()


class ZoneIndicator(Entity):
    def __init__(self, position, radius, tint):
        super().__init__(
            model="cube",
            position=Vec3(position.x, 0.05, position.z),
            scale=(0.1, 0.05, 0.1),
            color=tint,
        )
        self.target_radius = radius
        self.elapsed = 0.0
        self.duration = 0.32

    def update(self):
        if _entity_gone(self):
            return
        self.elapsed += time.dt
        progress = min(1.0, self.elapsed / self.duration)
        size = max(0.1, self.target_radius * 2.0 * progress)
        self.scale = Vec3(size, 0.05, size)


class PlayerStatusHUD(Entity):
    def __init__(self, owner, position, align_left=True):
        super().__init__(parent=camera.ui)
        self.owner = owner
        origin_x = -0.5 if align_left else 0.5
        self.text = Text(parent=self, position=position, origin=(origin_x, 0.5), scale=0.9, color=owner.color)

    def update(self):
        p = self.owner
        if getattr(p, "destroyed", False) or getattr(p, "dead", False):
            return
        cd1 = f"{p.cooldown1:.1f}" if p.cooldown1 > 0 else "ready"
        cd2 = f"{p.cooldown2:.1f}" if p.cooldown2 > 0 else "ready"
        statuses = [name for name, timer in p.statuses.items() if timer > 0]
        buffs = ",".join(statuses[:4]) if statuses else "-"
        
        self.text.text = f"{p.display_name}\nHP {int(p.hp)}/100 | S1 {cd1} | S2 {cd2}\n{buffs}"
        self.text.color = p.original_color


class BasePlayer(Entity):
    display_name = "Player"
    skill1_cooldown = 1.0
    skill2_cooldown = 1.0

    def __init__(self, start_pos, controls, color_skin, hud_position=(-0.85, 0.34), hud_align_left=True, **kwargs):
        super().__init__(model="cube", collider="box", color=color_skin, position=start_pos, scale=(1, 1, 1), **kwargs)
        self.original_color = color_skin
        self.hud = PlayerStatusHUD(self, hud_position, hud_align_left)
        self.hp = 100
        self.controls = controls
        self.enemy_target = None
        self.base_speed = 5.0
        self.move_speed = self.base_speed
        self.turn_rate = 1.0
        self.direction = Vec3(0, 0, 1)
        self.locked_direction = Vec3(0, 0, 1)
        self.prev_position = Vec3(self.position)
        self.state_timer = 0.0
        self.cooldown1 = 0.0
        self.cooldown2 = 0.0
        self.stun_timer = 0.0
        self.statuses = {}
        self.attack_fired = False
        self.sm = StateGraph("IDLE")
        self.setup_base_states()
        self.description = ""

    def setup_base_states(self):
        states = [
            "IDLE", "MOVE", "ATTACK", "STUNNED",
            "P1_S11_STARTUP", "P1_S11_ACTIVE", "P1_S11_RECOVERY",
            "P1_S12_STARTUP", "P1_S12_BURST", "P1_S12_RECOVERY",
            "P2_S21_HOP", "P2_S21_ACTIVE", "P2_S21_RECOVERY",
            "P2_S22_STARTUP", "P2_S22_ACTIVE", "P2_S22_RECOVERY",
        ]
        for state in states:
            self.sm.add_state(state)

        self.sm.add_edge("IDLE", "MOVE")
        self.sm.add_edge("MOVE", "IDLE")
        self.sm.add_edge("IDLE", "ATTACK", self.can_act)
        self.sm.add_edge("MOVE", "ATTACK", self.can_act)
        self.sm.add_edge("ATTACK", "IDLE")

        self.sm.add_edge("IDLE", "P1_S11_STARTUP", self._can_cast_skill1)
        self.sm.add_edge("MOVE", "P1_S11_STARTUP", self._can_cast_skill1)
        self.sm.add_edge("P1_S11_STARTUP", "P1_S11_ACTIVE")
        self.sm.add_edge("P1_S11_ACTIVE", "P1_S11_RECOVERY")
        self.sm.add_edge("P1_S11_RECOVERY", "IDLE")

        self.sm.add_edge("IDLE", "P1_S12_STARTUP", self._can_cast_skill2)
        self.sm.add_edge("MOVE", "P1_S12_STARTUP", self._can_cast_skill2)
        self.sm.add_edge("P1_S12_STARTUP", "P1_S12_BURST")
        self.sm.add_edge("P1_S12_BURST", "P1_S12_RECOVERY")
        self.sm.add_edge("P1_S12_RECOVERY", "IDLE")

        self.sm.add_edge("IDLE", "P2_S21_HOP", self._can_cast_skill1)
        self.sm.add_edge("MOVE", "P2_S21_HOP", self._can_cast_skill1)
        self.sm.add_edge("P2_S21_HOP", "P2_S21_ACTIVE")
        self.sm.add_edge("P2_S21_ACTIVE", "P2_S21_RECOVERY")
        self.sm.add_edge("P2_S21_RECOVERY", "IDLE")

        self.sm.add_edge("IDLE", "P2_S22_STARTUP", self._can_cast_skill2)
        self.sm.add_edge("MOVE", "P2_S22_STARTUP", self._can_cast_skill2)
        self.sm.add_edge("P2_S22_STARTUP", "P2_S22_ACTIVE")
        self.sm.add_edge("P2_S22_ACTIVE", "P2_S22_RECOVERY")
        self.sm.add_edge("P2_S22_RECOVERY", "IDLE")

        for state in states:
            if state != "STUNNED":
                self.sm.add_edge(state, "STUNNED", lambda: self.hp > 0)
        self.sm.add_edge("STUNNED", "IDLE", lambda: self.hp > 0)

    def _can_cast_skill1(self):
        return self.can_act() and self.cooldown1 <= 0

    def _can_cast_skill2(self):
        return self.can_act() and self.cooldown2 <= 0

    def can_act(self):
        return self.hp > 0 and self.sm.current_state in ("IDLE", "MOVE") and self.stun_timer <= 0

    def has_status(self, name):
        return self.statuses.get(name, 0.0) > 0

    def apply_status(self, name, duration):
        self.statuses[name] = max(self.statuses.get(name, 0.0), duration)

    def consume_status(self, name):
        if name in self.statuses:
            del self.statuses[name]

    def change_state(self, new_state):
        if self.sm.request_transition(new_state):
            self.state_timer = 0.0
            self.on_enter_state(new_state)
            return True
        return False

    def on_enter_state(self, new_state):
        if new_state in ("IDLE", "MOVE"):
            self.color = self.original_color
        elif new_state == "STUNNED":
            self.color = color.rgb(255, 240, 120)

    def common_update(self):
        dt = time.dt
        self.prev_position = Vec3(self.position)
        self.state_timer += dt
        if self.sm.current_state in ("IDLE", "MOVE", "ATTACK", "STUNNED"):
            self.cooldown1 = max(0.0, self.cooldown1 - dt)
            self.cooldown2 = max(0.0, self.cooldown2 - dt)

        expired = []
        for name in list(self.statuses.keys()):
            self.statuses[name] -= dt
            if self.statuses[name] <= 0:
                expired.append(name)
        for name in expired:
            del self.statuses[name]

        self.move_speed = self.base_speed * (0.8 if self.has_status("shackled") else 1.0)
        self.turn_rate = 0.65 if self.has_status("off_balance") else 1.0

        if self.stun_timer > 0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            if self.sm.current_state != "STUNNED":
                self.change_state("STUNNED")
            elif self.stun_timer <= 0:
                self.change_state("IDLE")

        if self.hp <= 0:
            self.color = color.black
            return False
        return True

    def handle_move(self):
        if self.sm.current_state not in ("IDLE", "MOVE"):
            return

        move_dir = Vec3(
            held_keys[self.controls["right"]] - held_keys[self.controls["left"]],
            0,
            held_keys[self.controls["up"]] - held_keys[self.controls["down"]],
        )

        if move_dir.length() <= 0:
            if self.sm.current_state == "MOVE":
                self.change_state("IDLE")
            return

        move_dir = move_dir.normalized()
        self.direction = move_dir
        self.locked_direction = move_dir
        target_rot = _angle_y(move_dir)
        self.rotation_y = lerp(self.rotation_y, target_rot, min(1.0, time.dt * 12 * self.turn_rate))
        old_pos = Vec3(self.position)
        new_pos = old_pos + move_dir * self.move_speed * time.dt
        if not check_world_collision(old_pos, new_pos, self.scale, [self]):
            self.position = new_pos
        if self.sm.current_state == "IDLE":
            self.change_state("MOVE")

    def execute_attack(self):
        if not self.can_act():
            return False
        if getattr(self, "active_attack", None) and not getattr(self.active_attack, "destroyed", False) and not getattr(self.active_attack, "dead", False):
            return False
        if not self.change_state("ATTACK"):
            return False
        self.locked_direction = _safe_dir(self.direction)
        self.attack_fired = False
        return True

    def _fire_attack(self):
        from combat import BasicProjectile
        spawn = self.position + Vec3(0, 0.25, 0) + self.locked_direction * 0.65
        self.active_attack = BasicProjectile(spawn, self.locked_direction, self, damage=6, speed=15.0)

    def take_damage(self, amount, source=None):
        self.hp = max(0, self.hp - amount)
        _spawn_fx(self.position + Vec3(0, 0.45, 0), 0.42, color.rgb(255, 120, 120), 0.08)

    def apply_stun(self, duration):
        self.stun_timer = max(self.stun_timer, duration)
        if self.sm.current_state != "STUNNED":
            self.change_state("STUNNED")

    def pull_toward(self, source, distance):
        if not _is_alive(source):
            return
        direction = _safe_dir(source.position - self.position, Vec3(0, 0, 1))
        target_pos = self.position + direction * distance
        clamped = _clamp_path(self, target_pos, [source])
        self.position = clamped

    def push_away_from(self, point, distance):
        direction = _safe_dir(self.position - point, self.direction)
        clamped = _clamp_path(self, self.position + direction * distance)
        self.position = clamped

    def update(self):
        if not self.common_update():
            return

        if held_keys[self.controls["attack"]] and self.sm.current_state in ("IDLE", "MOVE"):
            self.execute_attack()

        if self.sm.current_state == "ATTACK":
            if not self.attack_fired and self.state_timer >= 0.08:
                self.attack_fired = True
                self._fire_attack()
            if self.state_timer >= 0.30:
                self.change_state("IDLE")


class Player1(BasePlayer):
    display_name = "Dusthook Jailer"
    skill1_cooldown = 2
    skill2_cooldown = 2

    def __init__(self, start_pos, controls, hud_position=(-0.85, 0.34), hud_align_left=True, **kwargs):
        super().__init__(start_pos, controls, color.rgb(210, 170, 110), hud_position=hud_position, hud_align_left=hud_align_left, **kwargs)
        self.hook_projectile = None
        self.s11_recovery = 0.16
        self.s12_zone = None
        self.s12_center = Vec3(self.position)
        self.s12_recovery = 0.18
        self.description = (
            "Dusthook Jailer\n"
            "Skill 1 fires a hook that damages, pulls, and applies Shackled.\n"
            "Skill 2 detonates a sand pit in front; Shackled targets lose the mark and are stunned instead of pushed."
        )

    def execute_skill1(self):
        if not self.change_state("P1_S11_STARTUP"):
            return False
        self.cooldown1 = self.skill1_cooldown
        self.locked_direction = _safe_dir(self.direction)
        return True

    def execute_skill2(self):
        if not self.change_state("P1_S12_STARTUP"):
            return False
        self.cooldown2 = self.skill2_cooldown
        self.locked_direction = _safe_dir(self.direction)
        self.s12_center = self.position + self.locked_direction * 1.6
        self.s12_zone = ZoneIndicator(self.s12_center, 0.95, color.rgb(90, 70, 40))
        return True

    def on_enter_state(self, new_state):
        super().on_enter_state(new_state)
        if new_state == "P1_S11_STARTUP":
            self.color = color.rgb(175, 130, 70)
        elif new_state == "P1_S12_STARTUP":
            self.color = color.rgb(165, 140, 85)

    def _resolve_pitbreaker(self):
        enemy = _find_enemy(self)
        if not _is_alive(enemy):
            return
        if _distance_xz(enemy.position, self.s12_center) > 0.95 + enemy.scale.x * 0.25:
            return

        if enemy.has_status("shackled"):
            action_queue.push_action(2, enemy.consume_status, "shackled")
            action_queue.push_action(3, enemy.take_damage, 18, self)
            action_queue.push_action(6, enemy.apply_stun, 0.55)
        else:
            action_queue.push_action(3, enemy.take_damage, 12, self)
            action_queue.push_action(5, enemy.push_away_from, self.s12_center, 0.6)

    def _start_pitbreaker_burst(self):
        if self.s12_zone is not None and not getattr(self.s12_zone, "destroyed", False):
            destroy(self.s12_zone)
        self.change_state("P1_S12_BURST")
        _spawn_fx(self.s12_center + Vec3(0, 0.3, 0), (1.6, 0.8, 1.6), color.rgb(214, 185, 120), 0.14)
        self._resolve_pitbreaker()
        self.change_state("P1_S12_RECOVERY")

    def update(self):
        if not self.common_update():
            return

        if held_keys[self.controls["attack"]] and self.sm.current_state in ("IDLE", "MOVE"):
            self.execute_attack()

        if self.sm.current_state == "ATTACK":
            if not self.attack_fired and self.state_timer >= 0.08:
                self.attack_fired = True
                self._fire_attack()
            if self.state_timer >= 0.30:
                self.change_state("IDLE")
            return

        state = self.sm.current_state
        if state == "P1_S11_STARTUP" and self.state_timer >= 0.12:
            self.change_state("P1_S11_ACTIVE")
            self.hook_projectile = HookProjectile(self, self.locked_direction)
        elif state == "P1_S11_ACTIVE":
            self.change_state("P1_S11_RECOVERY")
        elif state == "P1_S11_RECOVERY" and self.state_timer >= self.s11_recovery:
            self.change_state("IDLE")
        elif state == "P1_S12_STARTUP" and self.state_timer >= 0.32:
            self._start_pitbreaker_burst()
        elif state == "P1_S12_RECOVERY" and self.state_timer >= self.s12_recovery:
            self.change_state("IDLE")
        elif state == "STUNNED" and self.stun_timer <= 0:
            self.change_state("IDLE")


class Player2(BasePlayer):
    display_name = "Springheel Ravager"
    skill1_cooldown = 2.0
    skill2_cooldown = 2.0

    def __init__(self, start_pos, controls, hud_position=(0.85, 0.34), hud_align_left=False, **kwargs):
        super().__init__(start_pos, controls, color.rgb(190, 225, 145), hud_position=hud_position, hud_align_left=hud_align_left, **kwargs)
        self.s21_start = Vec3(self.position)
        self.s21_hit_done = False
        self.s22_startup = 0.30
        self.s22_hit_done = False
        self.s22_origin = Vec3(self.position)
        self.description = (
            "Springheel Ravager\n"
            "Skill 1 is a short forward hop that clears straight projectiles and applies Off-Balance on landing.\n"
            "Skill 2 is an overhead chop that starts faster if any enemy is Off-Balance and stuns marked targets."
        )

    def execute_skill1(self):
        if not self.change_state("P2_S21_HOP"):
            return False
        self.cooldown1 = self.skill1_cooldown
        self.locked_direction = _safe_dir(self.direction)
        self.s21_start = Vec3(self.position)
        self.s21_hit_done = False
        return True

    def execute_skill2(self):
        if not self.can_act() or self.cooldown2 > 0:
            return False
        enemy = _find_enemy(self)
        self.s22_startup = 0.18 if _is_alive(enemy) and enemy.has_status("off_balance") else 0.30
        if not self.change_state("P2_S22_STARTUP"):
            return False
        self.cooldown2 = self.skill2_cooldown
        self.locked_direction = _safe_dir(self.direction)
        self.s22_hit_done = False
        self.s22_origin = Vec3(self.position)
        return True

    def on_enter_state(self, new_state):
        super().on_enter_state(new_state)
        if new_state == "P2_S21_HOP":
            self.color = color.rgb(230, 245, 170)
        elif new_state == "P2_S22_STARTUP":
            self.color = color.rgb(235, 250, 185)

    def _clear_projectiles_during_hop(self):
        for entity in list(scene.entities):
            if not _is_projectile(entity) or getattr(entity, "owner", None) is self or _entity_gone(entity):
                continue
            entity_pos, entity_scale = _entity_transform(entity)
            if entity_pos is None:
                continue
            if check_minkowski_collision(self.position, self.scale, entity_pos, entity_scale):
                action_queue.push_action(1, destroy, entity)
                _spawn_fx(entity_pos, 0.35, color.rgb(245, 235, 180), 0.08)

    def _resolve_hop_hit(self):
        if self.s21_hit_done:
            return
        enemy = _find_enemy(self)
        if not _half_circle_hit(self, enemy, 1.1):
            return
        self.s21_hit_done = True
        action_queue.push_action(2, enemy.apply_status, "off_balance", 2.0)
        action_queue.push_action(3, enemy.take_damage, 9, self)
        action_queue.push_action(5, enemy.push_away_from, self.position, 0.4)

    def _resolve_cleaver_hit(self):
        if self.s22_hit_done:
            return
        enemy = _find_enemy(self)
        if not _front_rect_hit(self.s22_origin, self.locked_direction, enemy, 1.9, 0.85):
            return
        self.s22_hit_done = True
        if enemy.has_status("off_balance"):
            action_queue.push_action(2, enemy.consume_status, "off_balance")
            action_queue.push_action(3, enemy.take_damage, 18, self)
            action_queue.push_action(6, enemy.apply_stun, 0.45)
        else:
            action_queue.push_action(3, enemy.take_damage, 13, self)
            action_queue.push_action(5, enemy.push_away_from, self.position, 0.45)

    def _start_hop_active(self):
        self.position = Vec3(self.position.x, 0.5, self.position.z)
        self.change_state("P2_S21_ACTIVE")
        self.rotation_y = _angle_y(self.locked_direction)
        self._resolve_hop_hit()
        _spawn_fx(
            self.position + self.locked_direction * 0.5 + Vec3(0, 0.25, 0),
            (0.9, 0.16, 0.5),
            color.rgb(255, 250, 220),
            0.08,
            _angle_y(self.locked_direction),
        )

    def _start_cleaver_active(self):
        self.change_state("P2_S22_ACTIVE")
        self.rotation_y = _angle_y(self.locked_direction)
        self._resolve_cleaver_hit()
        _spawn_fx(
            self.s22_origin + self.locked_direction * 0.95 + Vec3(0, 0.3, 0),
            (1.9, 0.18, 0.4),
            color.rgb(250, 245, 205),
            0.10,
            _angle_y(self.locked_direction),
        )

    def update(self):
        if not self.common_update():
            return

        if held_keys[self.controls["attack"]] and self.sm.current_state in ("IDLE", "MOVE"):
            self.execute_attack()

        if self.sm.current_state == "ATTACK":
            if not self.attack_fired and self.state_timer >= 0.08:
                self.attack_fired = True
                self._fire_attack()
            if self.state_timer >= 0.30:
                self.change_state("IDLE")
            return

        state = self.sm.current_state
        if state == "P2_S21_HOP":
            duration = 0.18
            progress = min(1.0, self.state_timer / duration)
            if self.state_timer >= duration - 0.001:
                desired = self.s21_start + self.locked_direction * 2.0
            else:
                desired = self.s21_start + self.locked_direction * (2.0 * progress)
            delta = desired - self.position
            if delta.length() > 0:
                _move_body_blocked(self, delta, _find_enemy(self))
            self.position = Vec3(self.position.x, 0.5 + math.sin(progress * math.pi) * 0.5, self.position.z)
            self.rotation_y = _angle_y(self.locked_direction)
            self._clear_projectiles_during_hop()
            _spawn_fx(self.position + Vec3(0, -0.35, 0), (0.22, 0.05, 0.22), color.rgb(220, 210, 150), 0.08)
            if self.state_timer >= duration:
                self._start_hop_active()
        elif state == "P2_S21_ACTIVE":
            self.rotation_y = _angle_y(self.locked_direction)
            if self.state_timer >= 0.08:
                self.change_state("P2_S21_RECOVERY")
        elif state == "P2_S21_RECOVERY" and self.state_timer >= 0.18:
            self.change_state("IDLE")
        elif state == "P2_S22_STARTUP":
            self.rotation_y = _angle_y(self.locked_direction)
            if self.state_timer >= self.s22_startup:
                self._start_cleaver_active()
        elif state == "P2_S22_ACTIVE":
            self.rotation_y = _angle_y(self.locked_direction)
            if self.state_timer >= 0.08:
                self.change_state("P2_S22_RECOVERY")
        elif state == "P2_S22_RECOVERY" and self.state_timer >= 0.18:
            self.change_state("IDLE")
        elif state == "STUNNED" and self.stun_timer <= 0:
            self.change_state("IDLE")
