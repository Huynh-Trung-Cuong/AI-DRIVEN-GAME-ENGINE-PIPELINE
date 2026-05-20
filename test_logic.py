import json
import subprocess
import sys


SCENARIOS = [
    "activation_and_recovery",
    "dusthook_and_pitbreaker_logic",
    "springheel_and_cleaver_logic",
    "cross_interactions",
]


def run_parent():
    results = []
    for scenario in SCENARIOS:
        proc = subprocess.run(
            [sys.executable, __file__, scenario],
            capture_output=True,
            text=True,
            check=False,
        )
        payload = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                payload = json.loads(line)
                break
        if payload is None:
            payload = {
                "scenario": scenario,
                "passed": False,
                "details": f"Missing JSON result. stderr={proc.stderr.strip()} stdout={proc.stdout.strip()}",
            }
        results.append(payload)

    failed = [result for result in results if not result["passed"]]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status} {result['scenario']}: {result['details']}")
    if failed:
        sys.exit(1)


def run_child(scenario_name):
    from ursina.window import Window

    Window.make_editor_gui = lambda self: None

    from ursina import Ursina, Vec3, destroy, scene, time

    app = Ursina(window_type="offscreen", development_mode=False)

    import player

    controls1 = {"up": "w", "down": "s", "left": "a", "right": "d", "attack": "1", "skill1": "2", "skill2": "3"}
    controls2 = {"up": "up arrow", "down": "down arrow", "left": "left arrow", "right": "right arrow", "attack": "j", "skill1": "n", "skill2": "m"}

    def make_players(p1_pos=(0, 0.5, 0), p2_pos=(0, 0.5, 1.0), p1_dir=(0, 0, 1), p2_dir=(0, 0, -1)):
        p1 = player.Player1(start_pos=Vec3(*p1_pos), controls=controls1)
        p2 = player.Player2(start_pos=Vec3(*p2_pos), controls=controls2)
        p1.enemy_target = p2
        p2.enemy_target = p1
        p1.direction = Vec3(*p1_dir)
        p2.direction = Vec3(*p2_dir)
        p1.locked_direction = Vec3(*p1_dir)
        p2.locked_direction = Vec3(*p2_dir)
        return p1, p2

    def active_entities():
        for entity in list(scene.entities):
            if getattr(entity, "destroyed", False):
                continue
            if getattr(entity, "dead", False):
                continue
            yield entity

    def tick(p1, p2, steps, dt=0.02):
        for _ in range(steps):
            time.dt = dt
            p1.update()
            p2.update()
            for entity in active_entities():
                if entity in (p1, p2):
                    continue
                update = getattr(entity, "update", None)
                if callable(update):
                    update()
            player.action_queue.process_all_actions()

    def count_entities(class_name):
        return sum(1 for entity in active_entities() if entity.__class__.__name__ == class_name)

    def approx(value, expected, tolerance=0.06):
        return abs(value - expected) <= tolerance

    def finish(result):
        for entity in list(scene.entities):
            if not getattr(entity, "destroyed", False):
                try:
                    destroy(entity)
                except Exception:
                    pass
        print(json.dumps(result))
        app.destroy()

    def activation_and_recovery():
        details = []

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.5))
        p1.execute_skill1()
        skill1_projectile_visible = False
        tick(p1, p2, 7)
        skill1_projectile_visible = count_entities("HookProjectile") > 0
        started = p1.sm.current_state in ("P1_S11_ACTIVE", "P1_S11_RECOVERY") and p1.cooldown1 == 5.5 and skill1_projectile_visible
        gated = not p1.execute_skill1() and p1.cooldown1 <= 5.5
        tick(p1, p2, 20)
        recovered = p1.sm.current_state == "IDLE"
        details.append(f"P1 S1 state={p1.sm.current_state} hook={skill1_projectile_visible}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.0))
        p1.execute_skill2()
        tick(p1, p2, 5)
        skill2_zone_visible = count_entities("ZoneIndicator") > 0
        started = started and p1.sm.current_state == "P1_S12_STARTUP" and p1.cooldown2 == 9.5 and skill2_zone_visible
        gated = gated and not p1.execute_skill2() and p1.cooldown2 <= 9.5
        tick(p1, p2, 20)
        recovered = recovered and p1.sm.current_state == "IDLE"
        details.append(f"P1 S2 state={p1.sm.current_state} zone={skill2_zone_visible}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.4))
        p2.execute_skill1()
        tick(p1, p2, 4)
        started = started and p2.sm.current_state == "P2_S21_HOP" and p2.cooldown1 == 8.0 and p2.position.y > 0.5
        gated = gated and not p2.execute_skill1() and p2.cooldown1 <= 8.0
        tick(p1, p2, 26)
        recovered = recovered and p2.sm.current_state == "IDLE"
        details.append(f"P2 S1 state={p2.sm.current_state} y={round(p2.position.y, 2)}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 1.4))
        p2.execute_skill2()
        tick(p1, p2, 4)
        started = started and p2.sm.current_state == "P2_S22_STARTUP" and p2.cooldown2 == 11.0
        gated = gated and not p2.execute_skill2() and p2.cooldown2 <= 11.0
        tick(p1, p2, 26)
        recovered = recovered and p2.sm.current_state == "IDLE"
        details.append(f"P2 S2 state={p2.sm.current_state} startup={p2.s22_startup}")

        finish(
            {
                "scenario": "activation_and_recovery",
                "passed": started and gated and recovered,
                "details": "; ".join(details),
            }
        )

    def dusthook_and_pitbreaker_logic():
        details = []

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.0))
        p1.execute_skill1()
        tick(p1, p2, 25)
        hook_ok = p2.hp == 92 and p2.has_status("shackled") and approx(p2.position.z, 1.1, 0.08)
        details.append(f"hook hp={p2.hp} shackled={p2.has_status('shackled')} z={round(p2.position.z, 2)}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.0))
        p1.execute_skill2()
        tick(p1, p2, 25)
        pit_base_ok = p2.hp == 88 and p2.stun_timer <= 0 and approx(p2.position.z, 2.6, 0.08)
        details.append(f"pit_base hp={p2.hp} stun={round(p2.stun_timer, 2)} z={round(p2.position.z, 2)}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.0))
        p2.apply_status("shackled", 2.2)
        p1.execute_skill2()
        tick(p1, p2, 25)
        pit_combo_ok = p2.hp == 82 and not p2.has_status("shackled") and p2.stun_timer > 0 and approx(p2.position.z, 2.0, 0.05)
        details.append(
            f"pit_combo hp={p2.hp} shackled={p2.has_status('shackled')} stun={round(p2.stun_timer, 2)} z={round(p2.position.z, 2)}"
        )

        finish(
            {
                "scenario": "dusthook_and_pitbreaker_logic",
                "passed": hook_ok and pit_base_ok and pit_combo_ok,
                "details": "; ".join(details),
            }
        )

    def springheel_and_cleaver_logic():
        details = []

        p1, p2 = make_players(p2_pos=(0, 0.5, 2.4))
        p2.execute_skill1()
        tick(p1, p2, 20)
        hop_ok = p1.hp == 91 and p1.has_status("off_balance") and approx(p1.position.z, -0.4, 0.08)
        details.append(f"hop hp={p1.hp} off_balance={p1.has_status('off_balance')} z={round(p1.position.z, 2)}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 1.4))
        p2.execute_skill2()
        tick(p1, p2, 25)
        cleaver_base_ok = p1.hp == 87 and p1.stun_timer <= 0 and approx(p1.position.z, -0.45, 0.08)
        details.append(f"cleaver_base hp={p1.hp} stun={round(p1.stun_timer, 2)} z={round(p1.position.z, 2)}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 1.4))
        p1.apply_status("off_balance", 2.0)
        p2.execute_skill2()
        startup_ok = approx(p2.s22_startup, 0.18, 0.001)
        tick(p1, p2, 14)
        cleaver_combo_ok = p1.hp == 82 and not p1.has_status("off_balance") and p1.stun_timer > 0
        details.append(
            f"cleaver_combo hp={p1.hp} off_balance={p1.has_status('off_balance')} stun={round(p1.stun_timer, 2)} startup={p2.s22_startup}"
        )

        finish(
            {
                "scenario": "springheel_and_cleaver_logic",
                "passed": hop_ok and cleaver_base_ok and startup_ok and cleaver_combo_ok,
                "details": "; ".join(details),
            }
        )

    def cross_interactions():
        details = []

        p1, p2 = make_players(p2_pos=(0, 0.5, 1.7))
        p1.execute_skill1()
        p2.execute_skill1()
        tick(p1, p2, 20)
        hook_vs_hop_ok = p2.hp == 100 and not p2.has_status("shackled") and count_entities("HookProjectile") == 0
        details.append(f"hook_vs_hop hp={p2.hp} shackled={p2.has_status('shackled')} hooks={count_entities('HookProjectile')}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 1.2), p2_dir=(1, 0, 0))
        p2.execute_skill2()
        p1.execute_skill1()
        tick(p1, p2, 30)
        hook_during_startup_ok = p2.hp == 92 and p1.hp == 100 and p2.sm.current_state == "IDLE" and approx(p2.locked_direction.x, 1.0, 0.001)
        details.append(
            f"hook_during_startup p1_hp={p1.hp} p2_hp={p2.hp} state={p2.sm.current_state} dir=({round(p2.locked_direction.x, 2)},{round(p2.locked_direction.z, 2)})"
        )

        p1, p2 = make_players(p2_pos=(0, 0.5, 3.0))
        p1.execute_skill2()
        tick(p1, p2, 7)
        p2.execute_skill1()
        tick(p1, p2, 12)
        simultaneous_burst_slash_ok = p1.hp == 91 and p2.hp == 88 and approx(p2.position.z, 0.4, 0.1)
        details.append(f"burst_slash p1_hp={p1.hp} p2_hp={p2.hp} p2_z={round(p2.position.z, 2)}")

        p1, p2 = make_players(p2_pos=(0, 0.5, 1.6))
        p2.apply_status("shackled", 2.0)
        p1.apply_status("off_balance", 2.0)
        p1.execute_skill2()
        tick(p1, p2, 7)
        p2.execute_skill2()
        tick(p1, p2, 12)
        simultaneous_stun_ok = p1.hp == 82 and p2.hp == 82 and p1.stun_timer > 0 and p2.stun_timer > 0
        details.append(
            f"double_stun p1_hp={p1.hp} p2_hp={p2.hp} p1_stun={round(p1.stun_timer, 2)} p2_stun={round(p2.stun_timer, 2)}"
        )

        finish(
            {
                "scenario": "cross_interactions",
                "passed": hook_vs_hop_ok and hook_during_startup_ok and simultaneous_burst_slash_ok and simultaneous_stun_ok,
                "details": "; ".join(details),
            }
        )

    locals()[scenario_name]()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        run_parent()
    else:
        run_child(sys.argv[1])
