from ursina import *
from dsa import StateGraph, check_minkowski_collision, check_minkowski_ccd, FrameActionHeap
import math


action_queue = FrameActionHeap()

ACTIVE_RAILS = []
ACTIVE_FROST_RINGS = []
ACTIVE_WALLS = []
GLOBAL_DELAYED_ACTIONS = []


def _v3(value):
    return Vec3(value[0], value[1], value[2])


def _flat(value):
    return Vec3(value.x, 0, value.z)


def _safe_dir(value, fallback=Vec3(0, 0, 1)):
    direction = _flat(_v3(value))
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
    return (_flat(_v3(a)) - _flat(_v3(b))).length()


def _is_alive(entity):
    return entity is not None and not getattr(entity, "destroyed", False) and getattr(entity, "hp", 1) > 0


def _is_projectile(entity):
    return getattr(entity, "__class__", type("", (), {})).__name__ == "BasicProjectile"


def _destroy_later(entity, delay=0):
    if entity is not None and not getattr(entity, "destroyed", False):
        destroy(entity, delay=delay)


def _safe_entity_transform(entity):
    try:
        return entity.position, entity.scale
    except Exception:
        return None, None


def _spawn_cube(pos, scale, tint, duration=0.18, rotation_y=0):
    fx = Entity(model="cube", color=tint, position=pos, scale=scale, rotation_y=rotation_y)
    fx.animate_scale(0, duration=duration)
    destroy(fx, delay=duration)
    return fx


def _point_in_oriented_box(point, center, facing, length, width, extra=0.0):
    rel = _flat(_v3(point) - _v3(center))
    facing = _safe_dir(facing)
    side = _perp(facing)
    along = rel.dot(facing)
    across = rel.dot(side)
    return abs(along) <= length * 0.5 + extra and abs(across) <= width * 0.5 + extra


def _segment_point_distance_xz(a, b, p):
    a = _flat(_v3(a))
    b = _flat(_v3(b))
    p = _flat(_v3(p))
    ab = b - a
    if ab.length() <= 0.001:
        return (p - a).length()
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.dot(ab)))
    closest = a + ab * t
    return (p - closest).length()


def _aabb_for_oriented_box(facing, length, width, height=1.0):
    facing = _safe_dir(facing)
    side = _perp(facing)
    return Vec3(
        abs(facing.x) * length + abs(side.x) * width,
        height,
        abs(facing.z) * length + abs(side.z) * width,
    )


def check_world_collision(old_pos, new_pos, size, ignore=None):
    ignore = set(ignore or [])
    for entity in list(scene.entities):
        if entity in ignore or getattr(entity, "destroyed", False):
            continue
        if getattr(entity, "is_ground", False):
            continue
        if not (getattr(entity, "is_terrain", False) or getattr(entity, "is_skill_wall", False)):
            continue
        entity_pos, entity_scale = _safe_entity_transform(entity)
        if entity_pos is None or entity_scale is None:
            continue
        if check_minkowski_ccd(old_pos, new_pos, size, entity_pos, entity_pos, entity_scale):
            return True
    return False


def _move_entity_ccd(entity, target_pos, ignore=None):
    old_pos = Vec3(entity.position)
    target_pos = Vec3(target_pos)
    if not check_world_collision(old_pos, target_pos, entity.scale, [entity] + list(ignore or [])):
        entity.position = target_pos
        return True

    x_only = Vec3(target_pos.x, old_pos.y, old_pos.z)
    z_only = Vec3(old_pos.x, old_pos.y, target_pos.z)
    moved = False
    if not check_world_collision(old_pos, x_only, entity.scale, [entity] + list(ignore or [])):
        entity.position = x_only
        old_pos = Vec3(entity.position)
        moved = True
    if not check_world_collision(old_pos, z_only, entity.scale, [entity] + list(ignore or [])):
        entity.position = z_only
        moved = True
    return moved


def schedule_global(delay, func, *args, **kwargs):
    GLOBAL_DELAYED_ACTIONS.append([delay, func, args, kwargs])


def _update_global_delayed(dt):
    for item in GLOBAL_DELAYED_ACTIONS[:]:
        item[0] -= dt
        if item[0] <= 0:
            GLOBAL_DELAYED_ACTIONS.remove(item)
            action_queue.push_action(6, item[1], *item[2], **item[3])


def _update_world_objects(dt):
    _update_global_delayed(dt)
    for rail in list(ACTIVE_RAILS):
        rail.tick(dt)
    for ring in list(ACTIVE_FROST_RINGS):
        ring.tick(dt)
    for wall in list(ACTIVE_WALLS):
        wall.tick(dt)


class CinderRail(Entity):
    def __init__(self, owner, start, end):
        self.owner = owner
        self.start = Vec3(start)
        self.end = Vec3(end)
        self.direction = _safe_dir(self.end - self.start, owner.direction)
        self.length = max(0.1, _distance_xz(self.start, self.end))
        self.width = 0.8
        self.lifetime = 3.2
        self.frozen_timer = 0.0
        self.frozen = False
        self.reserved_by = None
        self.deleted = False
        self.hit_cooldowns = {}
        self.created_order = getattr(owner, "rail_counter", 0)
        owner.rail_counter = self.created_order + 1
        center = (self.start + self.end) * 0.5
        super().__init__(
            model="cube",
            color=color.rgb(255, 82, 18),
            position=Vec3(center.x, 0.08, center.z),
            scale=(self.width, 0.08, self.length),
            rotation_y=_angle_y(self.direction),
        )
        self.is_cinder_rail = True
        self.flames = []
        for i in range(4):
            t = (i + 0.5) / 4.0
            p = self.start + (self.end - self.start) * t
            lash = Entity(
                model="cube",
                color=color.rgb(255, 145, 36),
                position=Vec3(p.x, 0.35, p.z),
                scale=(0.12, 0.55, 0.12),
                rotation_y=_angle_y(self.direction),
            )
            lash.animate_scale((0.12, 0.8, 0.12), duration=0.22, loop=True)
            self.flames.append(lash)
        ACTIVE_RAILS.append(self)

    @property
    def active(self):
        return not self.deleted and not getattr(self, "destroyed", False)

    def aabb_scale(self):
        return _aabb_for_oriented_box(self.direction, self.length, self.width, 0.4)

    def overlaps_entity(self, entity, extra=0.45):
        if not self.active:
            return False
        if not check_minkowski_collision(self.position, self.aabb_scale(), entity.position, entity.scale):
            return False
        return _point_in_oriented_box(entity.position, self.position, self.direction, self.length, self.width, extra)

    def touches_ring(self, ring):
        if not self.active:
            return False
        return _segment_point_distance_xz(self.start, self.end, ring.position) <= ring.radius + self.width * 0.5

    def touches_wall(self, wall):
        if not self.active:
            return False
        return check_minkowski_collision(self.position, self.aabb_scale(), wall.position, wall.scale)

    def freeze(self):
        if self.deleted or self.frozen:
            return
        self.frozen = True
        self.frozen_timer = 0.40
        self.color = color.rgb(170, 235, 255)
        for flame in self.flames:
            flame.enabled = False
        _spawn_cube(self.position + Vec3(0, 0.25, 0), (self.width + 0.2, 0.12, self.length), color.rgb(185, 240, 255), 0.18, self.rotation_y)

    def remove(self):
        if self.deleted:
            return
        self.deleted = True
        if self in ACTIVE_RAILS:
            ACTIVE_RAILS.remove(self)
        for flame in self.flames:
            _destroy_later(flame)
        _destroy_later(self)

    def resolve_contact(self, target, immediate=False):
        if self.frozen or self.deleted or self.reserved_by is not None or not _is_alive(target):
            return
        key = id(target)
        if self.hit_cooldowns.get(key, 0.0) > 0:
            return
        if self.overlaps_entity(target):
            self.hit_cooldowns[key] = 0.50
            action_queue.push_action(2, target.receive_attack, 4, self.owner, 0.0, "rail", "Cinder Rail")
            action_queue.push_action(3, target.apply_status, "singe", 1.25)
            _spawn_cube(target.position + Vec3(0, 0.35, 0), (0.55, 0.55, 0.55), color.rgb(255, 110, 25), 0.12)

    def tick(self, dt):
        if self.deleted:
            return
        if self.frozen:
            self.frozen_timer -= dt
            if self.frozen_timer <= 0:
                self.remove()
            return
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.remove()
            return
        for key in list(self.hit_cooldowns.keys()):
            self.hit_cooldowns[key] = max(0.0, self.hit_cooldowns[key] - dt)
        target = self.owner.enemy_target
        if _is_alive(target):
            self.resolve_contact(target)


class FrostRing(Entity):
    def __init__(self, owner, pos):
        self.owner = owner
        self.radius = 1.2
        self.lifetime = 3.0
        super().__init__(model="cube", color=color.rgb(115, 225, 255), position=Vec3(pos.x, 0.04, pos.z), scale=(0.1, 0.1, 0.1))
        self.visible = False
        self.is_frost_ring = True
        self.segments = []
        for i in range(16):
            angle = math.tau * i / 16
            segment_pos = self.position + Vec3(math.sin(angle) * self.radius, 0.05, math.cos(angle) * self.radius)
            segment = Entity(
                model="cube",
                color=color.rgb(145, 225, 255),
                position=segment_pos,
                scale=(0.18, 0.08, 0.42),
                rotation_y=math.degrees(angle),
            )
            segment.animate_scale((0.18, 0.16, 0.42), duration=0.35, loop=True)
            self.segments.append(segment)
        ACTIVE_FROST_RINGS.append(self)

    @property
    def active(self):
        return not getattr(self, "destroyed", False) and self.lifetime > 0

    def contains(self, entity):
        return _distance_xz(entity.position, self.position) <= self.radius

    def remove(self):
        if self in ACTIVE_FROST_RINGS:
            ACTIVE_FROST_RINGS.remove(self)
        for segment in self.segments:
            _destroy_later(segment)
        _destroy_later(self)

    def tick(self, dt):
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.remove()
            return
        enemy = self.owner.enemy_target
        if _is_alive(enemy) and self.contains(enemy):
            enemy.apply_status("frost_ring_slow", 0.08)
        for rail in list(ACTIVE_RAILS):
            if rail.owner is not self.owner and rail.touches_ring(self):
                action_queue.push_action(4, rail.freeze)


class IcebreakWall(Entity):
    def __init__(self, owner, pos, slide_dir, duration):
        self.owner = owner
        self.lifetime = duration
        self.slide_dir = _safe_dir(slide_dir)
        super().__init__(
            model="cube",
            color=color.rgb(120, 220, 255),
            position=Vec3(pos.x, 0.45, pos.z),
            scale=(1.8, 0.9, 0.35),
            rotation_y=_angle_y(self.slide_dir),
            collider="box",
        )
        self.is_skill_wall = True
        for offset in (-0.9, 0.9):
            end = self.position + _perp(self.slide_dir) * offset
            _spawn_cube(end + Vec3(0, 0.35, 0), (0.4, 0.8, 0.4), color.rgb(205, 245, 255), 0.25)
        ACTIVE_WALLS.append(self)
        self.delete_touching_rails()

    def delete_touching_rails(self):
        for rail in list(ACTIVE_RAILS):
            if rail.touches_wall(self):
                action_queue.push_action(4, rail.remove)

    def delete_touching_projectiles(self):
        for entity in list(scene.entities):
            if _is_projectile(entity) and getattr(entity, "owner", None) is not self.owner:
                entity_pos, entity_scale = _safe_entity_transform(entity)
                if entity_pos is None or entity_scale is None:
                    continue
                if check_minkowski_collision(self.position, self.scale, entity_pos, entity_scale):
                    action_queue.push_action(1, destroy, entity)

    def tick(self, dt):
        self.lifetime -= dt
        if self.lifetime <= 0:
            if self in ACTIVE_WALLS:
                ACTIVE_WALLS.remove(self)
            _destroy_later(self)
            return
        self.delete_touching_rails()
        self.delete_touching_projectiles()


class PlayerStatusHUD(Entity):
    def __init__(self, owner, position, align_left=True):
        super().__init__(parent=camera.ui)
        self.owner = owner
        origin_x = -0.5 if align_left else 0.5
        self.text = Text(parent=self, position=position, origin=(origin_x, 0.5), scale=0.9, color=owner.color)

    def update(self):
        p = self.owner
        if getattr(p, "destroyed", False):
            return
        cd1 = f"{p.cooldown1:.1f}" if p.cooldown1 > 0 else "ready"
        cd2 = f"{p.cooldown2:.1f}" if p.cooldown2 > 0 else "ready"
        statuses = [name for name, timer in p.statuses.items() if timer > 0]
        buffs = ",".join(statuses[:4]) if statuses else "-"
        if isinstance(p, Player1):
            rails = len([r for r in ACTIVE_RAILS if r.owner is p and not r.deleted])
            special = f"rails:{rails} burnout:{p.statuses.get('burnout', 0):.1f}"
            stacks = "brand on target" if _is_alive(p.enemy_target) and p.enemy_target.has_status("ember_brand") else "brand:-"
        else:
            ring = p.frost_ring.lifetime if p.frost_ring and p.frost_ring.active else 0.0
            special = f"ring:{ring:.1f} traction:{'yes' if p.shell_traction else 'no'}"
            stacks = f"plates:{p.cold_plates} exp:{p.cold_plate_timer:.1f}"
        self.text.text = f"{p.display_name}\nHP {int(p.hp)}/{int(p.max_hp)} | S1 {cd1} | S2 {cd2}\n{stacks}\n{buffs}\n{special}"


class BasePlayer(Entity):
    display_name = "Player"
    skill1_cooldown = 1.0
    skill2_cooldown = 1.0

    def __init__(self, start_pos, controls, color_skin, hud_position=(-0.85, 0.34), hud_align_left=True, **kwargs):
        super().__init__(model="cube", collider="box", color=color_skin, position=start_pos, scale=(1, 1, 1), **kwargs)
        self.hp = 100
        self.max_hp = 100
        self.controls = controls
        self.enemy_target = None
        self.base_speed = 5.0
        self.move_speed = self.base_speed
        self.direction = Vec3(0, 0, 1)
        self.prev_position = Vec3(self.position)
        self.state_timer = 0.0
        self.hitstun_timer = 0.0
        self.cooldown1 = 0.0
        self.cooldown2 = 0.0
        self.statuses = {}
        self.delayed_actions = []
        self.allow_movement = False
        self.sm = StateGraph("IDLE")
        self._setup_base_states()
        self.description = ""
        self.hud = PlayerStatusHUD(self, hud_position, hud_align_left)

    def _setup_base_states(self):
        states = [
            "IDLE", "MOVE", "ATTACK", "HITSTUN", "DEAD",
            "HR_S11_COIL", "HR_S11_RUSH", "HR_S11_RAIL_SPAWN", "HR_S11_RECOVERY",
            "HR_S12_SNAP", "HR_S12_PASS", "HR_S12_BACKBLAST", "HR_S12_RAW_STARTUP", "HR_S12_RAW_LUNGE", "HR_S12_RECOVERY",
            "RB_S21_STARTUP", "RB_S21_GUARD", "RB_S21_RECOVERY",
            "RB_S22_STARTUP", "RB_S22_SLIDE", "RB_S22_WALL", "RB_S22_RECOVERY",
        ]
        for state in states:
            self.sm.add_state(state)
        self.sm.add_edge("IDLE", "MOVE")
        self.sm.add_edge("MOVE", "IDLE")
        self.sm.add_edge("IDLE", "ATTACK")
        self.sm.add_edge("MOVE", "ATTACK")
        self.sm.add_edge("ATTACK", "IDLE")
        for state in ("IDLE", "MOVE"):
            self.sm.add_edge(state, "HR_S11_COIL", lambda: self._can_act() and self.cooldown1 <= 0 and not self.has_status("burnout"))
            self.sm.add_edge(state, "HR_S12_SNAP", lambda: self._can_act() and self.cooldown2 <= 0)
            self.sm.add_edge(state, "HR_S12_RAW_STARTUP", lambda: self._can_act() and self.cooldown2 <= 0)
            self.sm.add_edge(state, "RB_S21_STARTUP", lambda: self._can_act() and self.cooldown1 <= 0)
            self.sm.add_edge(state, "RB_S22_STARTUP", lambda: self._can_act() and self.cooldown2 <= 0)
        transitions = [
            ("HR_S11_COIL", "HR_S11_RUSH"), ("HR_S11_RUSH", "HR_S11_RAIL_SPAWN"), ("HR_S11_RAIL_SPAWN", "HR_S11_RECOVERY"), ("HR_S11_RECOVERY", "IDLE"),
            ("HR_S12_SNAP", "HR_S12_PASS"), ("HR_S12_PASS", "HR_S12_BACKBLAST"), ("HR_S12_BACKBLAST", "HR_S12_SNAP"), ("HR_S12_BACKBLAST", "HR_S12_RECOVERY"),
            ("HR_S12_RAW_STARTUP", "HR_S12_RAW_LUNGE"), ("HR_S12_RAW_LUNGE", "HR_S12_RECOVERY"), ("HR_S12_RECOVERY", "IDLE"),
            ("RB_S21_STARTUP", "RB_S21_GUARD"), ("RB_S21_GUARD", "RB_S21_RECOVERY"), ("RB_S21_RECOVERY", "IDLE"),
            ("RB_S22_STARTUP", "RB_S22_SLIDE"), ("RB_S22_SLIDE", "RB_S22_WALL"), ("RB_S22_WALL", "RB_S22_RECOVERY"), ("RB_S22_RECOVERY", "IDLE"),
        ]
        for start, end in transitions:
            self.sm.add_edge(start, end)
        for state in states:
            if state not in ("DEAD", "HITSTUN"):
                self.sm.add_edge(state, "HITSTUN", lambda: self.hp > 0)
                self.sm.add_edge(state, "DEAD")
        self.sm.add_edge("HITSTUN", "IDLE", lambda: self.hp > 0)
        self.sm.add_edge("HITSTUN", "DEAD")

    def _transition(self, new_state):
        if self.sm.current_state == new_state:
            return True
        if self.sm.request_transition(new_state):
            self.state_timer = 0.0
            self._on_enter_state(new_state)
            return True
        return False

    def _on_enter_state(self, state):
        self.allow_movement = False
        if state == "IDLE":
            self.color = self.original_color
        if state == "ATTACK":
            self.execute_attack()

    def _can_act(self):
        return self.hp > 0 and self.sm.current_state in ("IDLE", "MOVE") and self.hitstun_timer <= 0 and not self.has_status("deep_freeze") and not self.has_status("root")

    def has_status(self, name):
        return self.statuses.get(name, 0.0) > 0

    def apply_status(self, name, duration):
        if name in ("singe", "frost_ring_slow") and self.has_status("shell_traction") and self.sm.current_state == "RB_S22_SLIDE":
            return
        if name in ("root", "deep_freeze") and self.has_status("shell_traction") and self.sm.current_state == "RB_S22_SLIDE":
            return
        self.statuses[name] = max(self.statuses.get(name, 0.0), duration)
        if name == "deep_freeze":
            _spawn_cube(self.position + Vec3(0, 0.4, 0), (0.9, 0.9, 0.9), color.rgb(200, 245, 255), 0.35)

    def consume_status(self, name):
        if name in self.statuses:
            del self.statuses[name]

    def schedule_delayed(self, delay, func, *args, **kwargs):
        self.delayed_actions.append([delay, func, args, kwargs])

    def _tick_delayed(self, dt):
        for item in self.delayed_actions[:]:
            item[0] -= dt
            if item[0] <= 0:
                self.delayed_actions.remove(item)
                action_queue.push_action(6, item[1], *item[2], **item[3])

    def _tick_statuses(self, dt):
        for name in list(self.statuses.keys()):
            self.statuses[name] -= dt
            if self.statuses[name] <= 0:
                del self.statuses[name]

    def _refresh_move_speed(self):
        speed = self.base_speed
        if self.has_status("deep_freeze") or self.has_status("root"):
            speed = 0
        if self.has_status("singe"):
            speed *= 0.8
        if self.has_status("burnout"):
            speed *= 0.8
        if self.has_status("frost_ring_slow"):
            speed *= 0.75
        if self.sm.current_state == "RB_S21_GUARD":
            speed = self.base_speed * 0.45
        self.move_speed = speed

    def common_update(self):
        dt = time.dt
        if isinstance(self, Player1):
            _update_world_objects(dt)
        self.prev_position = Vec3(self.position)
        self.state_timer += dt
        self.cooldown1 = max(0.0, self.cooldown1 - dt)
        self.cooldown2 = max(0.0, self.cooldown2 - dt)
        self._tick_statuses(dt)
        self._tick_delayed(dt)
        if self.hitstun_timer > 0:
            self.hitstun_timer -= dt
            if self.hitstun_timer <= 0 and self.sm.current_state == "HITSTUN":
                self._transition("IDLE")
        self._refresh_move_speed()
        return self.hp > 0

    def execute_attack(self):
        from combat import BasicProjectile
        BasicProjectile(self.position + self.direction * 1.5, self.direction, self)

    def receive_attack(self, amount, source=None, hitstun=0.0, attack_kind="direct", source_name="Attack"):
        if self.hp <= 0:
            return
        if self.sm.current_state == "HR_S11_RUSH" and (attack_kind == "projectile" or _is_projectile(source)):
            return
        if self.sm.current_state == "HR_S12_SNAP":
            return
        amount = int(amount)
        if isinstance(self, Player2):
            amount = self.modify_incoming_damage(amount, source, attack_kind)
        self.hp = max(0, self.hp - amount)
        if amount > 0:
            _spawn_cube(self.position + Vec3(0, 0.45, 0), (0.45, 0.45, 0.45), color.rgb(255, 245, 185), 0.10)
        if hitstun > 0 and self.hp > 0:
            self.apply_hitstun(hitstun)
        if self.hp <= 0:
            self._transition("DEAD")

    def take_damage(self, amount, source=None):
        attack_kind = "projectile" if _is_projectile(source) else "direct"
        self.receive_attack(amount, source, 0.0, attack_kind, "Basic Projectile" if attack_kind == "projectile" else "Damage")

    def apply_hitstun(self, duration):
        if self.sm.current_state == "RB_S22_STARTUP":
            duration *= 0.2
        self.hitstun_timer = max(self.hitstun_timer, duration)
        if self.hp > 0:
            self._transition("HITSTUN")

    def update(self):
        self.common_update()
        if self.sm.current_state == "ATTACK" and self.state_timer >= 0.30:
            self._transition("IDLE")


class Player1(BasePlayer):
    display_name = "Hellspur Raksha"
    skill1_cooldown = 4.2
    skill2_cooldown = 7.4

    def __init__(self, start_pos, controls, **kwargs):
        self.original_color = color.rgb(205, 38, 22)
        super().__init__(start_pos, controls, self.original_color, (-0.86, 0.32), True, **kwargs)
        self.rail_counter = 0
        self.s11_locked_dir = Vec3(0, 0, 1)
        self.s11_dash_start = Vec3(self.position)
        self.s11_hit_any = False
        self.s11_hit_targets = set()
        self.s11_recovery = 0.26
        self.s12_queue = []
        self.s12_current_rail = None
        self.s12_pass_start = Vec3(self.position)
        self.s12_pass_end = Vec3(self.position)
        self.s12_hit_targets = set()
        self.s12_backblast_targets = set()
        self.s12_ignition_targets = set()
        self.s12_cancel_after_pass = False
        self.s12_circuit_mode = False
        self.s12_recovery = 0.10
        self.description = (
            "Hellspur Raksha\n"
            "P1 keys: WASD move, 1 normal projectile, 2 Blazeline Rush, 3 Hellsnap Circuit.\n"
            "Blazeline Rush: 6 body damage, 0.10s hitstun, Ember Brand 3.0s, then a Cinder Rail for 3.2s. "
            "Rail contact deals 4 damage, Singe 1.25s, and each rail hits once per 0.50s. Cooldown 4.2s.\n"
            "Hellsnap Circuit: consumes valid rails newest first. Each pass deals 5, backblast deals 5, and a branded target triggers "
            "Ignition Lock for 4 bonus damage plus 0.25s root. With no rails, raw lunge deals 8. Cooldown 7.4s.\n"
            "Combo tip: rush through the target to brand, use the rail as space control, then cash out with Circuit before Burnout. "
            "Counterplay: frontal rush into Carapace is reduced and feeds Cold Plate; Frost Ring can freeze your rails before Circuit."
        )

    def _on_enter_state(self, state):
        super()._on_enter_state(state)
        if state == "HR_S11_COIL":
            self.color = color.rgb(255, 95, 25)
            _spawn_cube(self.position + Vec3(0, -0.05, 0), (0.75, 0.16, 0.75), color.rgb(255, 92, 20), 0.08)
            _spawn_cube(self.position + Vec3(0.32, 0.6, 0), (0.12, 0.35, 0.12), color.rgb(20, 8, 8), 0.10)
            _spawn_cube(self.position + Vec3(-0.32, 0.6, 0), (0.12, 0.35, 0.12), color.rgb(20, 8, 8), 0.10)
        elif state == "HR_S11_RUSH":
            self.s11_dash_start = Vec3(self.position)
            self.s11_hit_targets = set()
            self.s11_hit_any = False
        elif state == "HR_S11_RAIL_SPAWN":
            self._spawn_cinder_rail()
        elif state == "HR_S12_SNAP":
            self._prepare_next_circuit_pass()
        elif state == "HR_S12_PASS":
            self.s12_hit_targets = set()
            _spawn_cube((self.s12_pass_start + self.s12_pass_end) * 0.5 + Vec3(0, 0.25, 0), (0.16, 0.22, 3.0), color.rgb(255, 80, 18), 0.16, _angle_y(self.direction))
        elif state == "HR_S12_BACKBLAST":
            self.s12_backblast_targets = set()
            for i in range(10):
                angle = math.tau * i / 10
                p = self.s12_pass_end + Vec3(math.sin(angle) * 0.55, 0.25, math.cos(angle) * 0.55)
                _spawn_cube(p, (0.14, 0.14, 0.5), color.rgb(255, 95, 24), 0.14, math.degrees(angle))
        elif state == "HR_S12_RAW_LUNGE":
            self.s12_pass_start = Vec3(self.position)
            self.s12_hit_targets = set()
        elif state == "HR_S12_RECOVERY":
            duration = 0.45 if self.s12_circuit_mode else 0.25
            self.apply_status("burnout", duration)
            _spawn_cube(self.position + Vec3(0, 0.35, 0), (0.9, 0.9, 0.9), color.rgb(80, 38, 30), duration)
            self.s12_circuit_mode = False

    def execute_skill1(self):
        if not self._can_act() or self.cooldown1 > 0 or self.has_status("burnout"):
            return False
        self.s11_locked_dir = _safe_dir(self.direction)
        fast_start = any(rail.overlaps_entity(self, 0.1) for rail in ACTIVE_RAILS if rail.active and not rail.frozen)
        self.s11_coil_duration = 0.03 if fast_start else 0.06
        if self._transition("HR_S11_COIL"):
            self.cooldown1 = self.skill1_cooldown
            return True
        return False

    def execute_skill2(self):
        if not self._can_act() or self.cooldown2 > 0:
            return False
        eligible = [rail for rail in ACTIVE_RAILS if rail.owner is self and rail.active and not rail.frozen and rail.reserved_by is None]
        eligible.sort(key=lambda rail: rail.created_order, reverse=True)
        if eligible:
            self.s12_circuit_mode = True
            self.s12_queue = eligible
            self.s12_cancel_after_pass = False
            for rail in eligible:
                rail.reserved_by = self
            if self._transition("HR_S12_SNAP"):
                self.cooldown2 = self.skill2_cooldown
                return True
            for rail in eligible:
                if rail.reserved_by is self:
                    rail.reserved_by = None
            self.s12_queue = []
            return False
        self.s12_circuit_mode = False
        if self._transition("HR_S12_RAW_STARTUP"):
            self.cooldown2 = self.skill2_cooldown
            return True
        return False

    def _spawn_cinder_rail(self):
        existing = [rail for rail in ACTIVE_RAILS if rail.owner is self and rail.active and rail.reserved_by is None]
        if len(existing) >= 2:
            existing.sort(key=lambda rail: rail.created_order)
            existing[0].remove()
        rail = CinderRail(self, self.s11_dash_start, Vec3(self.position))
        for ring in list(ACTIVE_FROST_RINGS):
            if rail.touches_ring(ring):
                rail.freeze()
        if not rail.frozen and _is_alive(self.enemy_target):
            rail.resolve_contact(self.enemy_target, immediate=True)

    def _rush_hit_target(self, target):
        if id(target) in self.s11_hit_targets:
            return
        self.s11_hit_targets.add(id(target))
        self.s11_hit_any = True
        action_queue.push_action(2, target.receive_attack, 6, self, 0.10, "melee_skill", "Blazeline Rush")
        action_queue.push_action(3, target.apply_status, "ember_brand", 3.0)
        _spawn_cube(target.position + Vec3(0, 0.4, 0), (0.55, 0.55, 0.55), color.rgb(255, 40, 18), 0.11)

    def _prepare_next_circuit_pass(self):
        self.s12_current_rail = None
        while self.s12_queue:
            rail = self.s12_queue.pop(0)
            if rail.active and not rail.frozen:
                self.s12_current_rail = rail
                d_start = _distance_xz(self.position, rail.start)
                d_end = _distance_xz(self.position, rail.end)
                if d_start <= d_end:
                    self.s12_pass_start = Vec3(rail.start)
                    self.s12_pass_end = Vec3(rail.end)
                else:
                    self.s12_pass_start = Vec3(rail.end)
                    self.s12_pass_end = Vec3(rail.start)
                self.position = Vec3(self.s12_pass_start.x, self.position.y, self.s12_pass_start.z)
                self.direction = _safe_dir(self.s12_pass_end - self.s12_pass_start)
                self.rotation_y = _angle_y(self.direction)
                _spawn_cube(self.position + Vec3(0, 0.35, 0), (0.45, 0.45, 0.45), color.rgb(255, 120, 25), 0.08)
                return
        self.s12_recovery = 0.10
        self._transition("HR_S12_RECOVERY")

    def _circuit_pass_hit(self, target):
        if id(target) in self.s12_hit_targets:
            return
        self.s12_hit_targets.add(id(target))
        action_queue.push_action(2, target.receive_attack, 5, self, 0.10, "melee_skill", "Hellsnap Pass")
        if target.has_status("ember_brand"):
            action_queue.push_action(3, target.consume_status, "ember_brand")
            self.s12_ignition_targets.add(target)
            _spawn_cube(target.position + Vec3(0, 0.65, 0), (0.25, 0.25, 0.25), color.rgb(45, 5, 5), 0.28)

    def _backblast_hit(self, target):
        if id(target) in self.s12_backblast_targets:
            return
        self.s12_backblast_targets.add(id(target))
        action_queue.push_action(2, target.receive_attack, 5, self, 0.14, "melee_skill", "Hellsnap Backblast")
        if target in self.s12_ignition_targets:
            schedule_global(0.18, self._apply_ignition_lock, target)

    def _apply_ignition_lock(self, target):
        if _is_alive(target):
            target.receive_attack(4, self, 0.0, "delayed", "Ignition Lock")
            target.apply_status("root", 0.25)

    def update(self):
        if not self.common_update():
            return
        state = self.sm.current_state
        if state == "ATTACK" and self.state_timer >= 0.30:
            self._transition("IDLE")
        elif state == "HR_S11_COIL" and self.state_timer >= self.s11_coil_duration:
            self._transition("HR_S11_RUSH")
        elif state == "HR_S11_RUSH":
            duration = 0.20
            old_pos = Vec3(self.position)
            progress = min(1.0, self.state_timer / duration)
            target_pos = self.s11_dash_start + self.s11_locked_dir * (3.0 * progress)
            _move_entity_ccd(self, target_pos, [self.enemy_target] if _is_alive(self.enemy_target) else [])
            _spawn_cube(self.position - self.s11_locked_dir * 0.45 + Vec3(0, 0.45, 0), (0.22, 0.22, 0.9), color.rgb(40, 10, 10), 0.08, _angle_y(self.s11_locked_dir))
            if _is_alive(self.enemy_target):
                if check_minkowski_ccd(old_pos, self.position, self.scale, self.enemy_target.prev_position, self.enemy_target.position, self.enemy_target.scale):
                    self._rush_hit_target(self.enemy_target)
            if self.state_timer >= duration:
                self.s11_recovery = 0.18 if self.s11_hit_any else 0.26
                self._transition("HR_S11_RAIL_SPAWN")
        elif state == "HR_S11_RAIL_SPAWN":
            self._transition("HR_S11_RECOVERY")
        elif state == "HR_S11_RECOVERY" and self.state_timer >= self.s11_recovery:
            self._transition("IDLE")
        elif state == "HR_S12_SNAP" and self.s12_current_rail is not None and self.state_timer >= 0.03:
            self._transition("HR_S12_PASS")
        elif state == "HR_S12_PASS":
            duration = 0.16
            old_pos = Vec3(self.position)
            progress = min(1.0, self.state_timer / duration)
            self.position = self.s12_pass_start + (self.s12_pass_end - self.s12_pass_start) * progress
            if _is_alive(self.enemy_target):
                pass_size = Vec3(1.0, 1.0, 1.0)
                if check_minkowski_ccd(old_pos, self.position, pass_size, self.enemy_target.prev_position, self.enemy_target.position, self.enemy_target.scale):
                    self._circuit_pass_hit(self.enemy_target)
                if isinstance(self.enemy_target, Player2) and self.enemy_target.sm.current_state == "RB_S22_SLIDE":
                    if check_minkowski_collision(self.position, pass_size, self.enemy_target.position, Vec3(1.9, 1.0, 1.9)):
                        self.s12_cancel_after_pass = True
            if self.state_timer >= duration:
                self._transition("HR_S12_BACKBLAST")
        elif state == "HR_S12_BACKBLAST":
            if _is_alive(self.enemy_target) and _distance_xz(self.enemy_target.position, self.s12_pass_end) <= 0.9:
                self._backblast_hit(self.enemy_target)
            if self.state_timer >= 0.12:
                if self.s12_current_rail is not None:
                    self.s12_current_rail.remove()
                self.s12_current_rail = None
                self.s12_ignition_targets = set()
                if self.s12_cancel_after_pass:
                    self.s12_queue = []
                if self.s12_queue:
                    self._transition("HR_S12_SNAP")
                else:
                    self._transition("HR_S12_RECOVERY")
        elif state == "HR_S12_RAW_STARTUP" and self.state_timer >= 0.08:
            self._transition("HR_S12_RAW_LUNGE")
        elif state == "HR_S12_RAW_LUNGE":
            duration = 0.12
            old_pos = Vec3(self.position)
            progress = min(1.0, self.state_timer / duration)
            target_pos = self.s12_pass_start + self.direction * (1.4 * progress)
            _move_entity_ccd(self, target_pos, [self.enemy_target] if _is_alive(self.enemy_target) else [])
            _spawn_cube(self.position + self.direction * 0.35 + Vec3(0, 0.4, 0), (0.28, 0.28, 1.4), color.rgb(255, 75, 20), 0.08, _angle_y(self.direction))
            if _is_alive(self.enemy_target) and id(self.enemy_target) not in self.s12_hit_targets:
                if check_minkowski_ccd(old_pos, self.position, Vec3(0.9, 1.0, 1.5), self.enemy_target.prev_position, self.enemy_target.position, self.enemy_target.scale):
                    self.s12_hit_targets.add(id(self.enemy_target))
                    action_queue.push_action(2, self.enemy_target.receive_attack, 8, self, 0.16, "melee_skill", "Raw Hellsnap Lunge")
            if self.state_timer >= duration:
                self.s12_recovery = 0.30
                self._transition("HR_S12_RECOVERY")
        elif state == "HR_S12_RECOVERY" and self.state_timer >= self.s12_recovery:
            self._transition("IDLE")


class Player2(BasePlayer):
    display_name = "Rimeback Bastion"
    skill1_cooldown = 5.8
    skill2_cooldown = 7.8

    def __init__(self, start_pos, controls, **kwargs):
        self.original_color = color.rgb(45, 135, 185)
        super().__init__(start_pos, controls, self.original_color, (0.86, 0.32), False, **kwargs)
        self.cold_plates = 0
        self.cold_plate_timer = 0.0
        self.plate_gain_timer = 0.0
        self.guard_pulse_cooldowns = {}
        self.frost_ring = None
        self.shell_traction = False
        self.s22_locked_dir = Vec3(0, 0, -1)
        self.s22_plates_spent = 0
        self.s22_slide_start = Vec3(self.position)
        self.s22_distance = 1.8
        self.s22_duration = 0.28
        self.s22_hit_done = False
        self.description = (
            "Rimeback Bastion\n"
            "P2 keys: Arrow keys move, J normal projectile, N Permafrost Carapace, M Siegebreak Slide.\n"
            "Permafrost Carapace: spawns Frost Ring for 3.0s, slows enemies 25%, freezes Cinder Rails, then guards for 1.20s. "
            "Front shell deletes projectiles or halves skill/body damage, grants Cold Plate, pulses 3 damage and Chill Stamp. Cooldown 5.8s.\n"
            "Siegebreak Slide: spends all Cold Plates. Slide deals 8 plus 2 per plate, stuns 0.18s, pushes, and consumes Chill Stamp into "
            "Deep Freeze for 0.35s. Launching from Frost Ring gives Shell Traction and a 3.0s wall. Cooldown 7.8s.\n"
            "Combo tip: guard the front to bank plates and Chill Stamp, then slide from inside Frost Ring. Counterplay: the slide is linear, "
            "rear hits bypass Carapace, and missed walls can be punished from the open side."
        )

    def _on_enter_state(self, state):
        super()._on_enter_state(state)
        if state == "RB_S21_STARTUP":
            self.frost_ring = FrostRing(self, Vec3(self.position))
            self.color = color.rgb(135, 220, 255)
            _spawn_cube(self.position + Vec3(0, 0.35, 0), (1.0, 0.8, 1.0), color.rgb(175, 235, 255), 0.16)
        elif state == "RB_S21_GUARD":
            self.allow_movement = True
        elif state == "RB_S22_STARTUP":
            self.s22_locked_dir = _safe_dir(self.direction)
            self.apply_status("shell_traction", 0.55 if self.shell_traction else 0.01)
            _spawn_cube(self.position + Vec3(0, 0.35, 0), (1.1, 0.9, 1.1), color.rgb(220, 250, 255), 0.18)
        elif state == "RB_S22_SLIDE":
            self.s22_slide_start = Vec3(self.position)
            self.s22_distance = 1.8 + 0.5 * self.s22_plates_spent
            self.s22_duration = 0.28 + 0.04 * self.s22_plates_spent
            self.s22_hit_done = False
        elif state == "RB_S22_WALL":
            duration = 3.0 if self.shell_traction else 2.0
            IcebreakWall(self, self.position + self.s22_locked_dir * 0.25, self.s22_locked_dir, duration)

    def execute_skill1(self):
        if not self._can_act() or self.cooldown1 > 0:
            return False
        if self._transition("RB_S21_STARTUP"):
            self.cooldown1 = self.skill1_cooldown
            return True
        return False

    def execute_skill2(self):
        if not self._can_act() or self.cooldown2 > 0:
            return False
        self.s22_plates_spent = self.cold_plates
        self.shell_traction = self.frost_ring is not None and self.frost_ring.active and self.frost_ring.contains(self)
        if self._transition("RB_S22_STARTUP"):
            self.cold_plates = 0
            self.cold_plate_timer = 0.0
            self.cooldown2 = self.skill2_cooldown
            return True
        return False

    def _is_front_arc(self, point, radius=1.1):
        offset = _flat(_v3(point) - self.position)
        if offset.length() > radius:
            return False
        if offset.length() <= 0.001:
            return True
        return _safe_dir(self.direction).dot(offset.normalized()) >= 0

    def _grant_plate(self):
        if self.plate_gain_timer > 0:
            return False
        self.cold_plates = min(3, self.cold_plates + 1)
        self.cold_plate_timer = 4.0
        self.plate_gain_timer = 0.20
        _spawn_cube(self.position + Vec3(0, 0.65, 0), (0.28, 0.28, 0.28), color.rgb(190, 240, 255), 0.16)
        return True

    def modify_incoming_damage(self, amount, source=None, attack_kind="direct"):
        if self.sm.current_state != "RB_S21_GUARD" or source is None:
            return amount
        source_pos, _ = _safe_entity_transform(source)
        if source_pos is None:
            source_pos = self.position
        if not self._is_front_arc(source_pos, 1.6):
            return amount
        if attack_kind == "projectile" or _is_projectile(source):
            action_queue.push_action(1, destroy, source)
            self._grant_plate()
            owner = getattr(source, "owner", None)
            if _is_alive(owner) and _distance_xz(owner.position, self.position) <= 1.6:
                action_queue.push_action(3, owner.apply_status, "chill_stamp", 2.5)
            return 0
        if attack_kind in ("melee_skill", "direct"):
            self._grant_plate()
            if _is_alive(source) and _distance_xz(source.position, self.position) <= 1.6:
                action_queue.push_action(3, source.apply_status, "chill_stamp", 2.5)
            return amount // 2
        return amount

    def _guard_projectiles(self):
        for entity in list(scene.entities):
            if not _is_projectile(entity) or getattr(entity, "owner", None) is self:
                continue
            entity_pos, _ = _safe_entity_transform(entity)
            if entity_pos is None:
                continue
            if self._is_front_arc(entity_pos, 1.1):
                action_queue.push_action(1, destroy, entity)
                self._grant_plate()
                owner = getattr(entity, "owner", None)
                if _is_alive(owner) and _distance_xz(owner.position, self.position) <= 1.6:
                    action_queue.push_action(3, owner.apply_status, "chill_stamp", 2.5)

    def _guard_enemy_pulse(self):
        enemy = self.enemy_target
        if not _is_alive(enemy) or not self._is_front_arc(enemy.position, 1.1):
            return
        key = id(enemy)
        if self.guard_pulse_cooldowns.get(key, 0.0) > 0:
            return
        self.guard_pulse_cooldowns[key] = 0.35
        action_queue.push_action(2, enemy.receive_attack, 3, self, 0.0, "shell_arc", "Carapace Pulse")
        if _distance_xz(enemy.position, self.position) <= 1.6:
            action_queue.push_action(3, enemy.apply_status, "chill_stamp", 2.5)
        push_dir = _safe_dir(enemy.position - self.position, self.direction)
        action_queue.push_action(5, _move_entity_ccd, enemy, enemy.position + push_dir * 0.25, [self])

    def _slide_hit_enemy(self):
        enemy = self.enemy_target
        if self.s22_hit_done or not _is_alive(enemy):
            return
        if not check_minkowski_collision(self.position, Vec3(1.9, 1.0, 1.9), enemy.position, enemy.scale):
            return
        self.s22_hit_done = True
        damage = 8 + 2 * self.s22_plates_spent
        push = 1.2 + 0.2 * self.s22_plates_spent
        had_stamp = enemy.has_status("chill_stamp")
        if had_stamp:
            action_queue.push_action(3, enemy.consume_status, "chill_stamp")
        action_queue.push_action(2, enemy.receive_attack, damage, self, 0.18, "melee_skill", "Siegebreak Slide")
        action_queue.push_action(5, _move_entity_ccd, enemy, enemy.position + self.s22_locked_dir * push, [self])
        if had_stamp:
            schedule_global(0.02, enemy.apply_status, "deep_freeze", 0.35)
        if isinstance(enemy, Player1) and enemy.sm.current_state == "HR_S12_PASS":
            enemy.s12_cancel_after_pass = True

    def _delete_rails_touched_by_slide(self):
        for rail in list(ACTIVE_RAILS):
            if rail.owner is not self and rail.overlaps_entity(self, 0.95):
                action_queue.push_action(4, rail.remove)

    def update(self):
        if not self.common_update():
            return
        dt = time.dt
        self.plate_gain_timer = max(0.0, self.plate_gain_timer - dt)
        for key in list(self.guard_pulse_cooldowns.keys()):
            self.guard_pulse_cooldowns[key] = max(0.0, self.guard_pulse_cooldowns[key] - dt)
        if self.cold_plate_timer > 0:
            self.cold_plate_timer -= dt
            if self.cold_plate_timer <= 0:
                self.cold_plates = 0
                self.cold_plate_timer = 0.0

        state = self.sm.current_state
        if state == "ATTACK" and self.state_timer >= 0.30:
            self._transition("IDLE")
        elif state == "RB_S21_STARTUP" and self.state_timer >= 0.10:
            self._transition("RB_S21_GUARD")
        elif state == "RB_S21_GUARD":
            self.allow_movement = True
            self.rotation_y = _angle_y(self.direction)
            _spawn_cube(self.position + self.direction * 0.45 + Vec3(0, 0.35, 0), (0.9, 0.12, 0.5), color.rgb(175, 235, 255), 0.06, _angle_y(self.direction))
            self._guard_projectiles()
            self._guard_enemy_pulse()
            if self.state_timer >= 1.20:
                self._transition("RB_S21_RECOVERY")
        elif state == "RB_S21_RECOVERY" and self.state_timer >= 0.22:
            self._transition("IDLE")
        elif state == "RB_S22_STARTUP" and self.state_timer >= 0.14:
            self._transition("RB_S22_SLIDE")
        elif state == "RB_S22_SLIDE":
            old_pos = Vec3(self.position)
            progress = min(1.0, self.state_timer / self.s22_duration)
            target_pos = self.s22_slide_start + self.s22_locked_dir * (self.s22_distance * progress)
            _move_entity_ccd(self, target_pos, [self.enemy_target] if _is_alive(self.enemy_target) else [])
            _spawn_cube(self.position - self.s22_locked_dir * 0.35 + Vec3(0, 0.12, 0), (0.65, 0.12, 0.45), color.rgb(155, 220, 255), 0.10, _angle_y(self.s22_locked_dir))
            if self.shell_traction:
                _spawn_cube(self.position + Vec3(0, 0.05, 0), (0.9, 0.08, 0.9), color.rgb(70, 165, 255), 0.08)
            self._slide_hit_enemy()
            self._delete_rails_touched_by_slide()
            if self.state_timer >= self.s22_duration or (old_pos - self.position).length() <= 0.001 and self.state_timer > 0.03:
                self._transition("RB_S22_WALL")
        elif state == "RB_S22_WALL":
            self._transition("RB_S22_RECOVERY")
        elif state == "RB_S22_RECOVERY" and self.state_timer >= 0.24:
            self.shell_traction = False
            self.consume_status("shell_traction")
            self._transition("IDLE")
