"""split-failures.py caps a track's size; split-errors.py gives each group the files it owns."""
from lib import check


def case_tracks_capped(s):
    lines = []
    for mod, count in (("a", 400), ("b", 150), ("c", 50)):
        lines += [f"test {mod}::tests::t{i:03} ... FAILED" for i in range(count)]
    log = s.work / "run.log"
    log.write_text("     Running unittests src/lib.rs (target/debug/deps/app-1)\n" + "\n".join(lines) + "\n")
    p = s.run("split-failures.py", str(s.work / "tracks"), "6", str(log))
    check(p.returncode == 0, "split-failures runs", p)
    groups = sorted((s.work / "tracks").glob("g*.md"))
    sizes = [int(g.read_text().split(": ", 1)[1].split()[0]) for g in groups]
    check(len(groups) >= 24 and max(sizes) <= 25 and sum(sizes) == 600,
          f"600 failures give at least 24 tracks of at most 25: {sizes}", p)
    p = s.run("split-failures.py", str(s.work / "few"), "2", str(log), "--max-per-track", "400")
    check(len(list((s.work / "few").glob("g*.md"))) == 2, "a higher cap keeps N groups", p)


def case_error_groups_own_files(s):
    errs = s.work / "errors"
    errs.write_text("".join(f"app/src/{f}.rs:{i}:1: error[E0425]: x\n" for f, n in (("a", 4), ("b", 4), ("shared", 1))
                            for i in range(1, n + 1)))
    p = s.run("split-errors.py", str(errs), "2", str(s.work / "g" / "cf"), cwd=s.work)
    check(p.returncode == 0, "split-errors runs", p)
    owned = [set((s.work / "g" / f"cf-{i}.files").read_text().split()) for i in (1, 2)]
    check(not owned[0] & owned[1] and owned[0] | owned[1] == {"app/src/a.rs", "app/src/b.rs", "app/src/shared.rs"},
          f"each file has one owner: {owned}", p)
