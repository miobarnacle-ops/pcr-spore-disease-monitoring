import pytest

from spore_patrol_teleop.control_logic import TeleopCommand, TeleopController


def test_motion_key_sets_command_until_timeout():
    controller = TeleopController(input_timeout_s=0.25)

    assert controller.handle_key("w", now=10.0) == "forward"
    assert controller.current_command(10.20) == TeleopCommand(0.05, 0.0)
    assert controller.current_command(10.26).is_zero


def test_turn_keys_use_angular_velocity_only():
    controller = TeleopController()

    controller.handle_key("a", now=1.0)
    assert controller.current_command(1.0) == TeleopCommand(0.0, 0.15)
    controller.handle_key("d", now=2.0)
    assert controller.current_command(2.0) == TeleopCommand(0.0, -0.15)


def test_stop_and_unknown_keys_are_zero():
    controller = TeleopController()
    controller.handle_key("w", now=1.0)
    assert controller.handle_key("x", now=1.1) == "stopped"
    assert controller.current_command(1.1).is_zero

    controller.handle_key("w", now=2.0)
    assert controller.handle_key("?", now=2.1) == "stopped"
    assert controller.current_command(2.1).is_zero


def test_speed_adjustment_is_bounded_and_stops_motion():
    controller = TeleopController(
        linear_speed_mps=0.14,
        angular_speed_radps=0.27,
    )
    controller.handle_key("w", now=1.0)
    assert controller.handle_key("+", now=1.1) == "speed_up"
    assert controller.current_command(1.1).is_zero
    assert controller.linear_speed_mps == pytest.approx(0.15)
    assert controller.angular_speed_radps == pytest.approx(0.30)

    controller.handle_key("-", now=1.2)
    assert controller.linear_speed_mps == pytest.approx(0.14)
    assert controller.angular_speed_radps == pytest.approx(0.27)


def test_quit_requests_stop():
    controller = TeleopController()
    controller.handle_key("w", now=1.0)
    assert controller.handle_key("q", now=1.1) == "quit"
    assert controller.current_command(1.1).is_zero
