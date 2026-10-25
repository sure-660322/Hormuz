"""Audit by default. --apply appends one transaction; source CSV stays local."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.case_ais import CASE_PREFIX, audit_csv
from backend.app.services.trajectory_cases import CASES, case_prefix


def import_case(connection, path, audit, *, case_id="arctic-ocean"):
    from sqlalchemy import text
    vessel = (dict(name="CSCL ARCTIC OCEAN", mmsi="477967700", imo="9695169", callsign="VROD9", length=400, width=58)
              if case_id == "arctic-ocean" else CASES[case_id])
    prefix = CASE_PREFIX if case_id == "arctic-ocean" else case_prefix(case_id)
    # Serialize case imports, including the no-existing-vessel branch.
    connection.execute(text("SELECT pg_advisory_xact_lock(477967700)"))
    previous = connection.execute(text("SELECT id,inserted_rows,source_file FROM ais_import_batches WHERE source_sha256=:hash"), {"hash": audit["sha256"]}).first()
    if previous:
        if previous.source_file != prefix + path.name:
            raise ValueError("File hash already belongs to another batch")
        actual = connection.scalar(text("SELECT count(*) FROM ship_positions WHERE source_batch_id=:id"), {"id": previous.id})
        if actual != audit["accepted_rows"] or previous.inserted_rows != actual:
            raise ValueError("Existing batch does not match audited count")
        return {"state": "already_imported", "batch_id": previous.id, "positions": actual}
    ship = connection.execute(text("SELECT id,imo FROM ships WHERE mmsi=:mmsi FOR UPDATE"), vessel).first()
    if ship and ship.imo not in (None, "", vessel["imo"]):
        raise ValueError("Existing MMSI has a conflicting IMO")
    if not ship:
        ship_id = connection.scalar(text("""INSERT INTO ships(mmsi,name,ship_type,ship_type_cn_raw,imo,callsign,flag,length_m,width_m)
          VALUES (:mmsi,:name,:type,:type,:imo,:callsign,:flag,:length,:width) RETURNING id"""),
          dict(vessel, type="集装箱船" if case_id == "arctic-ocean" else "油轮", flag="中国香港" if case_id == "arctic-ocean" else None))
    else:
        ship_id = ship.id
        if not ship.imo:
            connection.execute(text("UPDATE ships SET imo=:imo WHERE id=:id"), {"id":ship_id,"imo":vessel["imo"]})
    overlap = connection.scalar(text("SELECT count(*) FROM ship_positions WHERE ship_id=:id AND recorded_at BETWEEN :start AND :end"), dict(id=ship_id,start=audit["start_at"],end=audit["end_at"]))
    if overlap:
        raise ValueError("Vessel already has positions in this window; reconcile before importing")
    batch_id = connection.scalar(text("""INSERT INTO ais_import_batches(source_file,source_sha256,source_day,data_source,file_size_bytes,expected_rows,inserted_rows)
      VALUES (:file,:hash,:day,'nnu_ais',:size,:raw,0) RETURNING id"""), dict(file=prefix+path.name,hash=audit["sha256"],size=path.stat().st_size,raw=audit["raw_rows"],day=datetime.fromisoformat(audit["start_at"]).astimezone(timezone(timedelta(hours=8))).date()))
    values = [dict(p,ship_id=ship_id,batch_id=batch_id) for p in audit["positions"]]
    connection.execute(text("""INSERT INTO ship_positions(ship_id,latitude,longitude,speed,course,heading,recorded_at,unix_time,nav_status,rot,draught_m,destination,eta_text,ais_type,data_source,source_batch_id,source_row)
      VALUES (:ship_id,:latitude,:longitude,:speed,:course,:heading,:recorded_at,:unix_time,:nav_status,:rot,:draught_m,:destination,:eta_text,:ais_type,'nnu_ais',:batch_id,:source_row)"""), values)
    actual = connection.scalar(text("SELECT count(*) FROM ship_positions WHERE source_batch_id=:id AND location IS NOT NULL"), {"id":batch_id})
    if actual != audit["accepted_rows"]:
        raise ValueError("Inserted row count or generated location mismatch")
    connection.execute(text("UPDATE ais_import_batches SET inserted_rows=:n WHERE id=:id"), {"n":actual,"id":batch_id})
    return dict(state="imported",batch_id=batch_id,ship_id=ship_id,positions=actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--case", choices=["arctic-ocean", *CASES], default="arctic-ocean")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database", help="Explicit database name required for writes")
    args = parser.parse_args()
    vessel = CASES.get(args.case)
    audit_options = {}
    if vessel:
        audit_options = {k: vessel[k] for k in ("mmsi", "imo", "name")}
        audit_options.update(supplier="用户提供的 CSV；供应方与授权尚未核实",
                             quarantine_invalid_navigation=True)
    audit = audit_csv(args.csv, **audit_options)
    summary = {k:v for k,v in audit.items() if k != "positions"}
    summary["case_id"] = args.case
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    if args.apply:
        if not args.database:
            parser.error("--apply requires --database; back up the target before importing")
        from sqlalchemy import create_engine
        from backend.app.database import DATABASE_URL
        engine = create_engine(DATABASE_URL.set(database=args.database))
        with engine.begin() as connection:
            summary["import"] = import_case(connection,args.csv,audit,case_id=args.case)
        args.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("repaired_rows","quarantined_rows")},ensure_ascii=False))


if __name__ == "__main__":
    main()
