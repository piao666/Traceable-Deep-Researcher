"""Preview old unreferenced export files; deletion requires --apply."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.server.settings import ServerSettings
from backend.server.storage.database import Database
from backend.server.exports.maintenance import orphan_exports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url',default=ServerSettings.from_env().database_url)
    parser.add_argument('--min-age',type=float,default=86400)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();db=Database(args.database_url)
    try:
        print(json.dumps(orphan_exports(db,min_age=args.min_age,apply=args.apply),ensure_ascii=True))
    finally:db.dispose()


if __name__=='__main__':main()
