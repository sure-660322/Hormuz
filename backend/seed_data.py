from sqlalchemy import select
from datetime import datetime
from backend.app.database import SessionLocal
from backend.app.models import Event, Ship, ShipPosition


def seed_ships() -> None:
    with SessionLocal() as session:
        existing_ship_id = session.scalar(
            select(Ship.id).limit(1)
        )

        if existing_ship_id is not None:
            print("ships 表中已经存在数据，本次跳过插入")
            return

        ships = [
            Ship(
                mmsi="111000001",
                name="模拟货轮 A",
                ship_type="货轮",
                flag="模拟旗国",
                imo=None,
                callsign="SIM-A",
            ),
            Ship(
                mmsi="111000002",
                name="模拟油轮 B",
                ship_type="油轮",
                flag="模拟旗国",
                imo=None,
                callsign="SIM-B",
            ),
            Ship(
                mmsi="111000003",
                name="模拟集装箱船 C",
                ship_type="集装箱船",
                flag="模拟旗国",
                imo=None,
                callsign="SIM-C",
            ),
        ]

        session.add_all(ships)
        session.commit()

        print(f"已插入 {len(ships)} 艘模拟船舶")

def seed_positions() -> None:
    with SessionLocal() as session:
        existing_position_id = session.scalar(
            select(ShipPosition.id).limit(1)
        )

        if existing_position_id is not None:
            print("ship_positions 表中已经存在数据，本次跳过插入")
            return

        ships = {
            ship.mmsi: ship
            for ship in session.scalars(select(Ship)).all()
        }

        position_data = [
            ("111000001", 26.38, 55.95, 11.8, 95, 94, "2026-08-25T08:00:00+08:00"),
            ("111000001", 26.42, 56.05, 12.0, 95, 94, "2026-08-25T08:10:00+08:00"),
            ("111000001", 26.46, 56.17, 12.2, 95, 95, "2026-08-25T08:20:00+08:00"),
            ("111000001", 26.50, 56.30, 12.4, 95, 95, "2026-08-25T08:30:00+08:00"),

            ("111000002", 26.45, 56.75, 10.2, 275, 276, "2026-08-25T08:00:00+08:00"),
            ("111000002", 26.44, 56.65, 10.0, 275, 275, "2026-08-25T08:15:00+08:00"),
            ("111000002", 26.43, 56.55, 9.8, 275, None, "2026-08-25T08:30:00+08:00"),

            ("111000003", 26.70, 56.55, 14.7, 110, 111, "2026-08-25T08:00:00+08:00"),
            ("111000003", 26.66, 56.65, 14.9, 110, 110, "2026-08-25T08:15:00+08:00"),
            ("111000003", 26.62, 56.75, 15.1, 110, 110, "2026-08-25T08:30:00+08:00"),
        ]

        positions = [
            ShipPosition(
                data_source="simulation",
                ship_id=ships[mmsi].id,
                latitude=latitude,
                longitude=longitude,
                speed=speed,
                course=course,
                heading=heading,
                recorded_at=datetime.fromisoformat(recorded_at),
            )
            for (
                mmsi,
                latitude,
                longitude,
                speed,
                course,
                heading,
                recorded_at,
            ) in position_data
        ]

        session.add_all(positions)
        session.commit()

        print(f"已插入 {len(positions)} 条模拟船舶位置")

def seed_events() -> None:
    with SessionLocal() as session:
        existing_event_id = session.scalar(
            select(Event.id).limit(1)
        )

        if existing_event_id is not None:
            print("events 表中已经存在数据，本次跳过插入")
            return

        events = [
            Event(
                title="模拟冲突事件",
                description="用于练习地图事件展示的虚构事件，不代表真实情况。",
                event_type="conflict",
                latitude=26.55,
                longitude=56.48,
                occurred_at=datetime.fromisoformat(
                    "2026-08-25T09:00:00+08:00"
                ),
                source_name=None,
                source_url=None,
            ),
            Event(
                title="模拟航道管制事件",
                description="用于测试多个地图事件点的虚构航道管制信息。",
                event_type="navigation_control",
                latitude=26.62,
                longitude=56.68,
                occurred_at=datetime.fromisoformat(
                    "2026-08-25T10:00:00+08:00"
                ),
                source_name=None,
                source_url=None,
            ),
        ]

        session.add_all(events)
        session.commit()

        print(f"已插入 {len(events)} 条模拟事件")

if __name__ == "__main__":
    seed_ships()
    seed_positions()
    seed_events()