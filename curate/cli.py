import argparse, dataclasses, json, sys
from .config import Config
from .pipeline import run


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run.sh", description="Hindi/Hinglish corpus curation")
    ap.add_argument("raw_dir"); ap.add_argument("out_dir")
    for f in dataclasses.fields(Config):
        if f.name == "keep_langs":
            ap.add_argument("--keep-langs", default=",".join(f.default)); continue
        if f.type is bool:
            ap.add_argument(f"--{f.name.replace('_','-')}", action="store_true", default=f.default)
        else:
            ap.add_argument(f"--{f.name.replace('_','-')}", type=f.type, default=f.default)
    a = vars(ap.parse_args(argv))
    raw, out = a.pop("raw_dir"), a.pop("out_dir")
    a["keep_langs"] = tuple(x for x in a.pop("keep_langs").split(",") if x)
    manifest, secs = run(raw, out, Config(**a))
    print(json.dumps({"kept": manifest["kept_by_lang"], "eval": manifest["eval"]["n"],
                      "eval_leaks": manifest["eval"]["items_with_leaks"], "seconds": round(secs, 1)}), file=sys.stderr)


if __name__ == "__main__":
    main()
