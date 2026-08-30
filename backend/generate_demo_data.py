import argparse
import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from backend.app.database import SessionLocal
from backend.app.models import Event, Ship, ShipPosition


SHIP_COUNT = 150
POSITIONS_PER_SHIP = 96
EVENT_COUNT = 80
POSITION_INTERVAL_MINUTES = 5
RANDOM_SEED = 20260830

CHINA_TIMEZONE = timezone(timedelta(hours=8))

SIMULATION_START = datetime(
    2026,
    8,
    30,
    8,
    0,
    tzinfo=CHINA_TIMEZONE,
)

EASTBOUND_ROUTE = [
    (26.25, 54.60),
    (26.34, 55.20),
    (26.40, 55.80),
    (26.50, 56.20),
    (26.55, 56.60),
    (26.45, 57.10),
    (26.25, 57.80),
    (25.95, 58.50),
]

WESTBOUND_ROUTE = [
    (26.05, 58.50),
    (26.35, 57.80),
    (26.58, 57.10),
    (26.65, 56.60),
    (26.60, 56.20),
    (26.50, 55.80),
    (26.44, 55.20),
    (26.36, 54.60),
]

SHIP_TYPE_SPEED_RANGES = {
    "油轮": (8.0, 14.0),
    "货轮": (9.0, 16.0),
    "集装箱船": (12.0, 20.0),
    "客船": (14.0, 22.0),
    "拖轮": (4.0, 10.0),
}

EVENT_TYPES = [
    ("navigation_control", "模拟航道管制"),
    ("conflict", "模拟冲突风险"),
    ("bad_weather", "模拟恶劣天气"),
    ("equipment_failure", "模拟设备故障"),
    ("port_congestion", "模拟港口拥堵"),
]

PERIPHERAL_EVENT_SEA_ZONES = [
    (25.95, 26.15, 54.90, 55.60),
    (25.85, 26.15, 57.20, 58.20),
]

LOW_SPEED_SHIP_NUMBERS = set(range(1, 11))
STOPPED_SHIP_NUMBERS = set(range(11, 17))
DEVIATING_SHIP_NUMBERS = set(range(17, 25))

MIN_LATITUDE = 25.50
MAX_LATITUDE = 27.20
MIN_LONGITUDE = 54.40
MAX_LONGITUDE = 58.70
MAX_REASONABLE_SPEED_KNOTS = 35.0


def calculate_distance_km(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    start_latitude, start_longitude = start
    end_latitude, end_longitude = end

    start_latitude_radians = math.radians(start_latitude)
    end_latitude_radians = math.radians(end_latitude)
    latitude_difference = math.radians(
        end_latitude - start_latitude
    )
    longitude_difference = math.radians(
        end_longitude - start_longitude
    )

    haversine_value = (
        math.sin(latitude_difference / 2) ** 2
        + math.cos(start_latitude_radians)
        * math.cos(end_latitude_radians)
        * math.sin(longitude_difference / 2) ** 2
    )
    haversine_value = min(1.0, max(0.0, haversine_value))

    central_angle = 2 * math.atan2(
        math.sqrt(haversine_value),
        math.sqrt(1 - haversine_value),
    )

    return 6371.0088 * central_angle


def calculate_route_length_km(
    route: list[tuple[float, float]],
) -> float:
    return sum(
        calculate_distance_km(route[index], route[index + 1])
        for index in range(len(route) - 1)
    )


def get_point_along_route(
    route: list[tuple[float, float]],
    distance_km: float,
) -> tuple[float, float]:
    if distance_km <= 0:
        return route[0]

    remaining_distance = distance_km

    for index in range(len(route) - 1):
        start = route[index]
        end = route[index + 1]
        segment_length = calculate_distance_km(start, end)

        if remaining_distance <= segment_length:
            ratio = remaining_distance / segment_length

            latitude = start[0] + (end[0] - start[0]) * ratio
            longitude = start[1] + (end[1] - start[1]) * ratio

            return latitude, longitude

        remaining_distance -= segment_length

    return route[-1]


def calculate_course_degrees(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    start_latitude = math.radians(start[0])
    end_latitude = math.radians(end[0])
    longitude_difference = math.radians(end[1] - start[1])

    x = math.sin(longitude_difference) * math.cos(end_latitude)
    y = (
        math.cos(start_latitude) * math.sin(end_latitude)
        - math.sin(start_latitude)
        * math.cos(end_latitude)
        * math.cos(longitude_difference)
    )

    return (math.degrees(math.atan2(x, y)) + 360) % 360


def build_ships() -> list[Ship]:
    ship_types = list(SHIP_TYPE_SPEED_RANGES)
    simulated_flags = [
        "模拟甲旗",
        "模拟乙旗",
        "模拟丙旗",
        "模拟丁旗",
        "模拟戊旗",
    ]

    ships = []

    for ship_number in range(1, SHIP_COUNT + 1):
        ship_type = ship_types[
            (ship_number - 1) % len(ship_types)
        ]
        flag = simulated_flags[
            (ship_number - 1) % len(simulated_flags)
        ]

        ships.append(
            Ship(
                mmsi=f"900{ship_number:06d}",
                name=f"模拟{ship_type} {ship_number:03d}",
                ship_type=ship_type,
                flag=flag,
                imo=None,
                callsign=f"SIM{ship_number:03d}",
            )
        )

    return ships


def build_positions(
    ships: list[Ship],
    random_generator: random.Random,
) -> list[ShipPosition]:
    positions = []
    interval_hours = POSITION_INTERVAL_MINUTES / 60

    for ship_number, ship in enumerate(ships, start=1):
        if ship.id is None:
            raise ValueError("生成位置前，船舶必须已经具有数据库 ID")

        route = (
            EASTBOUND_ROUTE
            if ship_number % 2 == 1
            else WESTBOUND_ROUTE
        )
        route_length = calculate_route_length_km(route)
        minimum_speed, maximum_speed = SHIP_TYPE_SPEED_RANGES[
            ship.ship_type
        ]
        base_speed_knots = random_generator.uniform(
            minimum_speed,
            maximum_speed,
        )

        if ship_number in LOW_SPEED_SHIP_NUMBERS:
            base_speed_knots = random_generator.uniform(2.0, 3.5)

        moving_intervals = POSITIONS_PER_SHIP - 1
        if ship_number in STOPPED_SHIP_NUMBERS:
            moving_intervals -= 20

        maximum_travel_distance = (
            base_speed_knots
            * 1.852
            * interval_hours
            * moving_intervals
            * 1.04
        )
        maximum_start_distance = max(
            0.0,
            route_length - maximum_travel_distance - 5.0,
        )
        travelled_distance = random_generator.uniform(
            0.0,
            maximum_start_distance,
        )
        latitude_offset = random_generator.uniform(-0.015, 0.015)
        longitude_offset = random_generator.uniform(-0.010, 0.010)

        track_points = []

        for point_index in range(POSITIONS_PER_SHIP):
            if point_index > 0:
                is_stopped = (
                    ship_number in STOPPED_SHIP_NUMBERS
                    and 40 <= point_index < 60
                )

                if not is_stopped:
                    speed_variation = 1 + 0.04 * math.sin(
                        point_index / 8 + ship_number
                    )
                    current_speed_knots = (
                        base_speed_knots * speed_variation
                    )
                    travelled_distance += (
                        current_speed_knots
                        * 1.852
                        * interval_hours
                    )

            latitude, longitude = get_point_along_route(
                route,
                travelled_distance,
            )
            latitude += latitude_offset
            longitude += longitude_offset

            if ship_number in DEVIATING_SHIP_NUMBERS:
                if 35 <= point_index <= 55:
                    deviation_progress = (point_index - 35) / 20
                    latitude += 0.06 * math.sin(
                        math.pi * deviation_progress
                    )

            track_points.append((latitude, longitude))

        previous_course = calculate_course_degrees(
            track_points[0],
            track_points[1],
        )

        for point_index, point in enumerate(track_points):
            if point_index == 0:
                segment_start = track_points[0]
                segment_end = track_points[1]
            else:
                segment_start = track_points[point_index - 1]
                segment_end = point

            segment_distance = calculate_distance_km(
                segment_start,
                segment_end,
            )
            speed_knots = segment_distance / interval_hours / 1.852

            if segment_distance >= 0.001:
                course = calculate_course_degrees(
                    segment_start,
                    segment_end,
                )
                previous_course = course
            else:
                course = previous_course

            heading = (
                None
                if (ship_number + point_index) % 17 == 0
                else (
                    course + random_generator.uniform(-3.0, 3.0)
                )
                % 360
            )

            positions.append(
                ShipPosition(
                    ship_id=ship.id,
                    latitude=round(point[0], 6),
                    longitude=round(point[1], 6),
                    speed=round(speed_knots, 2),
                    course=round(course, 2),
                    heading=(
                        None
                        if heading is None
                        else round(heading, 2)
                    ),
                    recorded_at=(
                        SIMULATION_START
                        + timedelta(
                            minutes=(
                                point_index
                                * POSITION_INTERVAL_MINUTES
                            )
                        )
                    ),
                )
            )

    return positions


def build_events(
    positions: list[ShipPosition],
    random_generator: random.Random,
) -> list[Event]:
    events = []
    latest_positions = positions[
        POSITIONS_PER_SHIP - 1 :: POSITIONS_PER_SHIP
    ]

    for event_index in range(EVENT_COUNT):
        event_type, title_prefix = EVENT_TYPES[
            event_index % len(EVENT_TYPES)
        ]

        if event_index < 30:
            nearby_position = latest_positions[
                (event_index * 5) % len(latest_positions)
            ]
            latitude_direction = 1 if event_index % 2 == 0 else -1
            longitude_direction = 1 if event_index % 3 else -1
            latitude = (
                nearby_position.latitude
                + latitude_direction
                * random_generator.uniform(0.010, 0.035)
            )
            longitude = (
                nearby_position.longitude
                + longitude_direction
                * random_generator.uniform(0.010, 0.035)
            )
        elif event_index < 60:
            route = (
                EASTBOUND_ROUTE
                if event_index % 2 == 0
                else WESTBOUND_ROUTE
            )
            route_distance = random_generator.uniform(
                40.0,
                calculate_route_length_km(route) - 40.0,
            )
            latitude, longitude = get_point_along_route(
                route,
                route_distance,
            )
            latitude += random_generator.uniform(-0.035, 0.035)
            longitude += random_generator.uniform(-0.035, 0.035)
        else:
            (
                minimum_latitude,
                maximum_latitude,
                minimum_longitude,
                maximum_longitude,
            ) = PERIPHERAL_EVENT_SEA_ZONES[
                event_index % len(PERIPHERAL_EVENT_SEA_ZONES)
            ]
            latitude = random_generator.uniform(
                minimum_latitude,
                maximum_latitude,
            )
            longitude = random_generator.uniform(
                minimum_longitude,
                maximum_longitude,
            )

        occurred_at = SIMULATION_START + timedelta(
            minutes=(
                random_generator.randrange(POSITIONS_PER_SHIP)
                * POSITION_INTERVAL_MINUTES
            )
        )

        events.append(
            Event(
                title=f"{title_prefix} {event_index + 1:03d}",
                description=(
                    "用于霍尔木兹海峡态势地图功能演示的"
                    "教学模拟事件，不代表真实情况。"
                ),
                event_type=event_type,
                latitude=round(latitude, 6),
                longitude=round(longitude, 6),
                occurred_at=occurred_at,
                source_name="系统模拟",
                source_url=None,
            )
        )

    return events


def validate_generated_objects(
    ships: list[Ship],
    positions: list[ShipPosition],
    events: list[Event],
) -> None:
    if len(ships) != SHIP_COUNT:
        raise ValueError(f"船舶数量错误：{len(ships)}")

    if len(positions) != SHIP_COUNT * POSITIONS_PER_SHIP:
        raise ValueError(f"位置数量错误：{len(positions)}")

    if len(events) != EVENT_COUNT:
        raise ValueError(f"事件数量错误：{len(events)}")

    mmsi_values = [ship.mmsi for ship in ships]
    if len(set(mmsi_values)) != SHIP_COUNT:
        raise ValueError("模拟 MMSI 存在重复")

    position_counts = {}
    position_times = {}

    for position in positions:
        if not MIN_LATITUDE <= position.latitude <= MAX_LATITUDE:
            raise ValueError(f"位置纬度越界：{position.latitude}")
        if not MIN_LONGITUDE <= position.longitude <= MAX_LONGITUDE:
            raise ValueError(f"位置经度越界：{position.longitude}")
        if not 0 <= position.speed <= MAX_REASONABLE_SPEED_KNOTS:
            raise ValueError(f"位置速度异常：{position.speed}")
        if not 0 <= position.course < 360:
            raise ValueError(f"位置航向异常：{position.course}")
        if position.heading is not None and not 0 <= position.heading < 360:
            raise ValueError(f"船首向异常：{position.heading}")

        position_counts[position.ship_id] = (
            position_counts.get(position.ship_id, 0) + 1
        )
        position_times.setdefault(position.ship_id, []).append(
            position.recorded_at
        )

    if len(position_counts) != SHIP_COUNT:
        raise ValueError("并非每艘船都有位置记录")

    if set(position_counts.values()) != {POSITIONS_PER_SHIP}:
        raise ValueError("每艘船的位置数量不一致")

    for ship_id, recorded_times in position_times.items():
        if recorded_times != sorted(recorded_times):
            raise ValueError(f"船舶 {ship_id} 的位置时间没有递增")
        if len(set(recorded_times)) != POSITIONS_PER_SHIP:
            raise ValueError(f"船舶 {ship_id} 存在重复时间")

    for event in events:
        if not MIN_LATITUDE <= event.latitude <= MAX_LATITUDE:
            raise ValueError(f"事件纬度越界：{event.latitude}")
        if not MIN_LONGITUDE <= event.longitude <= MAX_LONGITUDE:
            raise ValueError(f"事件经度越界：{event.longitude}")
        if not (
            SIMULATION_START
            <= event.occurred_at
            <= SIMULATION_START
            + timedelta(
                minutes=(
                    (POSITIONS_PER_SHIP - 1)
                    * POSITION_INTERVAL_MINUTES
                )
            )
        ):
            raise ValueError(f"事件时间越界：{event.occurred_at}")


def validate_database(session) -> dict[str, int]:
    ship_count = session.scalar(
        select(func.count()).select_from(Ship)
    )
    position_count = session.scalar(
        select(func.count()).select_from(ShipPosition)
    )
    event_count = session.scalar(
        select(func.count()).select_from(Event)
    )
    unique_mmsi_count = session.scalar(
        select(func.count(func.distinct(Ship.mmsi)))
    )

    per_ship_counts = (
        select(
            ShipPosition.ship_id,
            func.count(ShipPosition.id).label("position_count"),
        )
        .group_by(ShipPosition.ship_id)
        .subquery()
    )
    ship_group_count, minimum_positions, maximum_positions = (
        session.execute(
            select(
                func.count(per_ship_counts.c.ship_id),
                func.min(per_ship_counts.c.position_count),
                func.max(per_ship_counts.c.position_count),
            )
        ).one()
    )

    expected_position_count = SHIP_COUNT * POSITIONS_PER_SHIP
    if (
        ship_count != SHIP_COUNT
        or position_count != expected_position_count
        or event_count != EVENT_COUNT
        or unique_mmsi_count != SHIP_COUNT
        or ship_group_count != SHIP_COUNT
        or minimum_positions != POSITIONS_PER_SHIP
        or maximum_positions != POSITIONS_PER_SHIP
    ):
        raise ValueError(
            "数据库验收失败："
            f"ships={ship_count}, "
            f"positions={position_count}, "
            f"events={event_count}, "
            f"unique_mmsi={unique_mmsi_count}, "
            f"ship_groups={ship_group_count}, "
            f"min_positions={minimum_positions}, "
            f"max_positions={maximum_positions}"
        )

    return {
        "ships": int(ship_count),
        "positions": int(position_count),
        "events": int(event_count),
    }


def build_preview_data() -> tuple[
    list[Ship],
    list[ShipPosition],
    list[Event],
]:
    random_generator = random.Random(RANDOM_SEED)
    ships = build_ships()

    for ship_id, ship in enumerate(ships, start=1):
        ship.id = ship_id

    positions = build_positions(ships, random_generator)
    events = build_events(positions, random_generator)
    validate_generated_objects(ships, positions, events)

    return ships, positions, events


def generate_demo_data() -> dict[str, int]:
    random_generator = random.Random(RANDOM_SEED)

    with SessionLocal() as session:
        with session.begin():
            session.execute(
                text(
                    "TRUNCATE TABLE "
                    "ship_positions, events, ships "
                    "RESTART IDENTITY"
                )
            )

            ships = build_ships()
            session.add_all(ships)
            session.flush()

            positions = build_positions(ships, random_generator)
            events = build_events(positions, random_generator)
            validate_generated_objects(ships, positions, events)

            session.add_all(positions)
            session.add_all(events)
            session.flush()

            database_counts = validate_database(session)

    return database_counts


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成霍尔木兹态势地图教学模拟数据",
    )
    action_group = parser.add_mutually_exclusive_group(
        required=True,
    )
    action_group.add_argument(
        "--validate-only",
        action="store_true",
        help="只在内存中生成和检查，不修改数据库",
    )
    action_group.add_argument(
        "--confirm-reset",
        action="store_true",
        help="确认清空并重建三张业务表中的模拟数据",
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    if arguments.validate_only:
        ships, positions, events = build_preview_data()
        maximum_speed = max(position.speed for position in positions)
        print("内存验收通过，不会修改数据库")
        print(f"船舶：{len(ships)}")
        print(f"位置：{len(positions)}")
        print(f"事件：{len(events)}")
        print(f"最高模拟速度：{maximum_speed:.2f} 节")
        return

    counts = generate_demo_data()
    print("模拟数据已重建并通过数据库验收")
    print(f"船舶：{counts['ships']}")
    print(f"位置：{counts['positions']}")
    print(f"事件：{counts['events']}")
    print(f"随机种子：{RANDOM_SEED}")


if __name__ == "__main__":
    main()
