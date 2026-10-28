"""Huecos libres recortados a las horas despierto del usuario."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.tools.waking_hours import clip_to_waking_hours

MX = ZoneInfo("America/Mexico_City")  # UTC-6 sin horario de verano
SCHEDULE = {
    "wake_weekday": "06:30",
    "sleep_weekday": "23:00",
    "wake_weekend": "09:00",
    "sleep_weekend": "01:00",
    "timezone": "America/Mexico_City",
}


def _mx(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=MX)  # 2 nov 2026 = lunes


def test_un_hueco_nocturno_se_descarta():
    slots = [(_mx(2, 23, 30), _mx(3, 5))]
    assert clip_to_waking_hours(slots, SCHEDULE, None, 25) == []


def test_un_hueco_que_cruza_la_hora_de_dormir_o_despertar_se_recorta():
    slots = [(_mx(2, 21), _mx(3, 8))]
    assert clip_to_waking_hours(slots, SCHEDULE, None, 25) == [
        (_mx(2, 21), _mx(2, 23)),
        (_mx(3, 6, 30), _mx(3, 8)),
    ]


def test_el_recorte_deja_un_resto_menor_a_la_duracion_y_se_descarta():
    slots = [(_mx(2, 22, 50), _mx(3, 7))]
    assert clip_to_waking_hours(slots, SCHEDULE, None, 25) == [(_mx(3, 6, 30), _mx(3, 7))]


def test_fin_de_semana_usa_su_propio_horario_y_dormir_pasada_la_medianoche():
    # sabado 7 nov: despierta 09:00; duerme 01:00 del domingo
    slots = [(_mx(7, 6), _mx(8, 3))]
    assert clip_to_waking_hours(slots, SCHEDULE, None, 25) == [(_mx(7, 9), _mx(8, 1))]


def test_sin_horario_guardado_usa_el_de_dia_por_defecto():
    slots = [(_mx(2, 3), _mx(2, 8))]
    assert clip_to_waking_hours(slots, {}, "America/Mexico_City", 25) == [(_mx(2, 7), _mx(2, 8))]


def test_sin_zona_horaria_conocida_no_recorta():
    slots = [(_mx(2, 3), _mx(2, 8))]
    assert clip_to_waking_hours(slots, {}, None, 25) == slots


def test_la_zona_del_horario_guardado_manda_sobre_la_de_la_peticion():
    utc = timezone.utc
    slots = [(datetime(2026, 11, 2, 12, 0, tzinfo=utc), datetime(2026, 11, 2, 13, 0, tzinfo=utc))]  # 06:00-07:00 MX
    assert clip_to_waking_hours(slots, SCHEDULE, "Asia/Tokyo", 25) == [
        (datetime(2026, 11, 2, 12, 30, tzinfo=utc), datetime(2026, 11, 2, 13, 0, tzinfo=utc))
    ]


def test_el_primer_hueco_ofrecible_deja_margen_y_redondea_a_5_min():
    from app.tools.waking_hours import earliest_start

    antes = _mx(2, 8)
    assert earliest_start(_mx(2, 11, 40), antes) == _mx(2, 11, 50)
    assert earliest_start(_mx(2, 11, 41), antes) == _mx(2, 11, 55)
    assert earliest_start(_mx(2, 11, 40), _mx(2, 13)) == _mx(2, 13)  # una ventana futura no se adelanta
