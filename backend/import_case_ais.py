"""Audit by default. --apply appends one transaction; source CSV stays local."""
import argparse
import json
from pathlib import Path

from backend.case_ais import CASE_PREFIX, audit_csv


def import_case(connection, path, audit):
    from sqlalchemy import text
    # Serialize case imports, including the no-existing-vessel branch.
    connection.execute(text("SELECT pg_advisory_xact_lock(477967700)"))
    previous = connection.execute(text("SELECT id,inserted_rows,source_file FROM ais_import_batches WHERE source_sha256=:hash"), {"hash": audit["sha256"]}).first()
    if previous:
        if previous.source_file != CASE_PREFIX + path.name:
            raise ValueError("File hash already belongs to another batch")
        actual = connection.scalar(text("SELECT count(*) FROM ship_positions WHERE source_batch_id=:id"), {"id": previous.id})
        if actual != audit["accepted_rows"] or previous.inserted_rows != actual:
            raise ValueError("Existing batch does not match audited count")
        return {"state": "already_imported", "batch_id": previous.id, "positions": actual}
    ship = connection.execute(text("SELECT id,imo FROM ships WHERE mmsi='477967700' FOR UPDATE")).first()
    if ship and ship.imo not in (None, "", "9695169"):
        raise ValueError("Existing MMSI has a conflicting IMO")
    if not ship:
        ship_id = connection.scalar(text("""INSERT INTO ships(mmsi,name,ship_type,ship_type_cn_raw,imo,callsign,flag,length_m,width_m)
          VALUES ('477967700','CSCL ARCTIC OCEAN','集装箱船','集装箱船','9695169','VROD9','中国香港',400,58) RETURNING id"""))
    else:
        ship_id = ship.id
        if not ship.imo:
            connection.execute(text("UPDATE ships SET imo='9695169' WHERE id=:id"), {"id":ship_id})
    overlap = connection.scalar(text("SELECT count(*) FROM ship_positions WHERE ship_id=:id AND recorded_at BETWEEN :start AND :end"), dict(id=ship_id,start=audit["start_at"],end=audit["end_at"]))
    if overlap:
        raise ValueError("Vessel already has positions in this window; reconcile before importing")
    batch_id = connection.scalar(text("""INSERT INTO ais_import_batches(source_file,source_sha256,source_day,data_source,file_size_bytes,expected_rows,inserted_rows)
      VALUES (:file,:hash,'2026-03-27','nnu_ais',:size,:raw,0) RETURNING id"""), dict(file=CASE_PREFIX+path.name,hash=audit["sha256"],size=path.stat().st_size,raw=audit["raw_rows"]))
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
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database", help="Explicit database name required for writes")
    args = parser.parse_args()
    audit = audit_csv(args.csv)
    summary = {k:v for k,v in audit.items() if k != "positions"}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    if args.apply:
        if not args.database:
            parser.error("--apply requires --database; back up the target before importing")
        from sqlalchemy import create_engine
        from backend.app.database import DATABASE_URL
        engine = create_engine(DATABASE_URL.set(database=args.database))
        with engine.begin() as connection:
            summary["import"] = import_case(connection,args.csv,audit)
        args.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("repaired_rows","quarantined_rows")},ensure_ascii=False))


if __name__ == "__main__":
    main()
