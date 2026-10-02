"""Read-only MusicDB query-plan audit with explicitly synthetic PC benchmarks."""
import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import time

QUERY = "SELECT * FROM Music WHERE (AudioState='2' OR AudioState=2) AND (ChartState='2' OR ChartState=2) ORDER BY Title, Artist"


def audit(path):
    path = Path(path).resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if 'Music' not in tables:
            return dict(filename=str(path), status='unsupported_schema', tables=tables,
                        limitation='No OG Music table. Do not apply the OG query or index proposal to later-generation databases.')
        return dict(filename=str(path), status='analyzed', tables=tables,
                    rows=connection.execute('SELECT count(*) FROM Music').fetchone()[0],
                    indexes=connection.execute('PRAGMA index_list(Music)').fetchall(),
                    query=QUERY, query_plan=connection.execute('EXPLAIN QUERY PLAN ' + QUERY).fetchall(),
                    sqlite_version=sqlite3.sqlite_version,
                    limitation='Desktop SQLite planner; console/profile database may have a different schema or planner.')
    except sqlite3.DatabaseError as error:
        return dict(filename=str(path), status='unreadable', error=str(error),
                    limitation='Desktop SQLite could not inspect this file. This does not identify the cause or prove the game has a corrupt database. No repair attempted.')
    finally:
        connection.close()


def benchmark(count, indexed=False, repeats=15):
    # No real metadata or game database is copied. Timing excludes container
    # discovery, native index objects, disk I/O, jackets, UI and the console CPU.
    connection = sqlite3.connect(':memory:')
    try:
        connection.execute('CREATE TABLE Music (ID, Title, Artist, AudioState, ChartState)')
        connection.executemany('INSERT INTO Music VALUES (?,?,?,?,?)',
                               ((i, f'Synthetic {count-i:06}', f'Artist {i % 20}', 2, 2) for i in range(count)))
        if indexed:
            connection.execute('CREATE INDEX synthetic_title_artist ON Music(Title, Artist)')
        plan = connection.execute('EXPLAIN QUERY PLAN ' + QUERY).fetchall()
        timings = []
        for _ in range(repeats):
            start = time.perf_counter()
            rows = connection.execute(QUERY).fetchall()
            timings.append((time.perf_counter() - start) * 1000)
        return dict(rows=count, returned=len(rows), indexed=indexed,
                    median_ms=statistics.median(timings), query_plan=plan)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = dict(database=audit(args.database),
                  synthetic_pc_benchmarks=[benchmark(n, indexed) for n in (40, 600, 2000) for indexed in (False, True)],
                  warning='Not Xbox timings; not a demonstrated lag cause or a tested optimization. No game database modified.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
