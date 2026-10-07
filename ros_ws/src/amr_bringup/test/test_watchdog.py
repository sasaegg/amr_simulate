import pytest

from amr_bringup.watchdog import Watchdog

TIMEOUT = 0.5


@pytest.fixture
def dog():
    return Watchdog(TIMEOUT)


def test_no_stop_before_any_command(dog):
    # 啟動後還沒收過指令：車子本來就停著，不需要送停車指令
    assert not dog.check(0.0)
    assert not dog.check(10.0)


def test_no_stop_within_timeout(dog):
    dog.on_command(0.0)
    assert not dog.check(0.1)
    assert not dog.check(0.49)


def test_stop_once_at_timeout(dog):
    dog.on_command(0.0)
    assert dog.check(0.5)            # 剛好到逾時就送停車
    assert not dog.check(0.6)        # 之後不重複狂送
    assert not dog.check(5.0)


def test_continuous_commands_never_stop(dog):
    for i in range(50):
        t = i * 0.1
        dog.on_command(t)
        assert not dog.check(t + 0.05)


def test_new_command_rearms_after_stop(dog):
    dog.on_command(0.0)
    assert dog.check(0.5)
    dog.on_command(1.0)              # 恢復送指令：重新開始計時
    assert not dog.check(1.4)
    assert dog.check(1.5)            # 再次逾時又會送一次停車
    assert not dog.check(1.6)


def test_late_check_still_stops_once(dog):
    # 計時器延遲很久才呼叫 check：仍然只送一次
    dog.on_command(0.0)
    assert dog.check(3.0)
    assert not dog.check(3.1)


def test_clock_jumping_backwards_does_not_stop(dog):
    # 模擬時間被重設（例如 Gazebo reset）時，時間會倒退；不能因此誤判逾時
    dog.on_command(10.0)
    assert not dog.check(2.0)
    assert dog.check(2.5)            # 以倒退後的時間重新計時


@pytest.mark.parametrize('timeout', [0, -1])
def test_timeout_must_be_positive(timeout):
    with pytest.raises(ValueError):
        Watchdog(timeout)
