"""A throwaway nod project to watch the live dashboard move.

    .venv/bin/python scripts/sandbox.py              # seed, serve, open browser, play the scenario
    .venv/bin/python scripts/sandbox.py --seed-only  # seed and serve; drive it yourself or with an agent
    .venv/bin/python scripts/sandbox.py --step 1     # faster scenario (seconds between moves)

The sandbox is a fresh git repository in tmp/sandbox, rebuilt on every run. Everything
goes through the nod CLI of this checkout, the same way an agent would drive it.
"""
import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOD = [sys.executable, "-c", "from nod.cli.app import app; app()"]


class Sandbox:
    def __init__(self, root: Path, step: float):
        self.root, self.step = root, step

    def nod(self, *args) -> str:
        out = subprocess.run([*NOD, *args], cwd=self.root, text=True, capture_output=True)
        if out.returncode:
            raise SystemExit(f"nod {' '.join(args)} failed:\n{out.stderr}")
        return out.stdout

    def add(self, title, **options) -> str:
        """Create a work item, return its identifier. Options are task add flags."""
        flags = [x for key, value in options.items() for x in (f"--{key.replace('_', '-')}", str(value))]
        return json.loads(self.nod("task", "add", title, *flags, "--json"))["identifier"]

    def move(self, note: str, identifier: str, status: str, **options):
        """One visible step of the scenario: say it, do it, give the page time to show it."""
        flags = [x for key, value in options.items() for x in (f"--{key.replace('_', '-')}", str(value))]
        print(f"  {identifier:8} {status:12} {note}", flush=True)
        self.nod("task", "set", identifier, "--status", status, *flags)
        time.sleep(self.step)

    def seed(self) -> dict:
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.nod("init", "--identifier", "DEMO", "--name", "Sandbox shop")

        def day(offset):
            return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()  # nod's clock is UTC

        for name in ("API", "Web", "Docs"):
            self.nod("module", "add", name)
        self.nod("cycle", "add", "Sprint 1", "--start", day(-21), "--end", day(-8), "--description", "Foundations.")
        self.nod("cycle", "add", "Sprint 2", "--start", day(-7), "--end", day(6), "--description", "Checkout, end to end.")
        self.nod("cycle", "add", "Sprint 3", "--start", day(7), "--end", day(20), "--description", "Polish and launch.")
        self.nod("cycle", "set", "sprint-1", "--status", "completed")
        self.nod("cycle", "set", "sprint-2", "--status", "active")

        history = (("Project skeleton", "api", -20, 5), ("Product list page", "web", -18, 9), ("README and setup guide", "docs", -12, 2))
        for title, module, started, hours in history:
            done = self.add(title, module=module, cycle="sprint-1", estimate="3h", status="in_progress")
            self.nod("task", "set", done, "--status", "done")  # stages go in order, then the history is backdated
            self.nod("task", "set", done, "--started-at", f"{day(started)}T09:00:00",
                     "--completed-at", f"{day(started)}T{9 + hours:02d}:00:00")

        epic = self.add("Checkout flow", type="epic", module="web", cycle="sprint-2", priority="high")
        s2 = dict(cycle="sprint-2", parent=epic)
        cart_api = self.add("Cart API", module="api", estimate="4h", priority="high", **s2)
        cart_page = self.add("Cart page", module="web", estimate="3h", **s2)
        payment = self.add("Payment provider client", module="api", estimate="5h", priority="urgent", **s2)
        checkout = self.add("Checkout form", module="web", estimate="4h", **s2)
        rounding = self.add("Totals round wrong for 3 items", type="bug", module="api", estimate="1h",
                            priority="high", due=day(-1), **s2)
        guide = self.add("Checkout guide", module="docs", estimate="2h", priority="low", **s2)
        self.nod("depends", cart_page, cart_api)
        self.nod("depends", checkout, payment)
        self.nod("depends", checkout, cart_page)

        emails = self.add("Order confirmation emails", module="api", cycle="sprint-3", estimate="3h")
        self.add("Empty states and loading", module="web", cycle="sprint-3", estimate="2h")
        self.add("Launch checklist", module="docs", cycle="sprint-3", estimate="1h", status="backlog")
        self.add("Dark mode", module="web", status="backlog", priority="low")
        self.add("Try a faster JSON library", status="backlog", priority="low")
        return dict(epic=epic, cart_api=cart_api, cart_page=cart_page, payment=payment,
                    checkout=checkout, rounding=rounding, guide=guide, emails=emails)

    def play(self, ids: dict):
        """Two agents working sprint 2 in parallel, a blocked item, then the cycle rolls over."""
        i = ids
        print("Scenario: two agents work Sprint 2, then the cycle rolls over.", flush=True)
        time.sleep(self.step)
        self.move("epic opens", i["epic"], "in_progress")
        self.move("agent A picks the overdue bug", i["rounding"], "in_progress", branch="fix/totals-rounding")
        self.move("agent B starts the cart API", i["cart_api"], "in_progress", branch="feat/cart-api")
        self.move("bug fixed", i["rounding"], "done")
        self.move("agent A takes the urgent one", i["payment"], "in_progress", branch="feat/payment-client")
        self.move("cart API merged", i["cart_api"], "done")
        self.move("agent B moves to the cart page", i["cart_page"], "in_progress", branch="feat/cart-page")
        self.move("waiting on provider keys", i["payment"], "hold")
        self.move("agent A fills the gap with docs", i["guide"], "in_progress", branch="docs/checkout-guide")
        self.move("cart page merged", i["cart_page"], "done")
        self.move("keys arrived, back on it", i["payment"], "in_progress")
        self.move("guide written", i["guide"], "done")
        self.move("payment client merged", i["payment"], "done")
        self.move("last item of the sprint", i["checkout"], "in_progress", branch="feat/checkout-form")
        self.move("checkout form merged", i["checkout"], "done")
        self.move("epic closed", i["epic"], "done")
        print("  Sprint 2 completed, Sprint 3 active", flush=True)
        self.nod("cycle", "set", "sprint-2", "--status", "completed")
        self.nod("cycle", "set", "sprint-3", "--status", "active")
        time.sleep(self.step)
        self.move("first item of the new sprint", i["emails"], "in_progress", branch="feat/order-emails")
        print("Scenario done.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=Path("tmp/sandbox"), help="Sandbox folder, wiped on every run.")
    parser.add_argument("--step", type=float, default=3, help="Seconds between scenario moves.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed-only", action="store_true", help="Seed and serve, do not play the scenario.")
    parser.add_argument("--no-serve", action="store_true", help="No server and no browser, for scripts and tests.")
    args = parser.parse_args()

    root = args.dir.resolve()
    if root.exists() and any(root.iterdir()) and not (root / ".nod").exists():
        raise SystemExit(f"{root} is not a nod sandbox, refusing to wipe it.")  # never delete a folder we did not make
    sandbox = Sandbox(root, args.step)
    ids = sandbox.seed()
    print(f"Seeded {root}")

    server = None
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # a plain kill still stops the server below
    try:
        if not args.no_serve:
            server = subprocess.Popen([*NOD, "serve", "--port", str(args.port)], cwd=root)
            time.sleep(1.5)
            if server.poll() is not None:
                raise SystemExit("nod serve did not start (port in use? try --port).")
            webbrowser.open(f"http://127.0.0.1:{args.port}/")
        if not args.seed_only:
            sandbox.play(ids)
        if server:
            print(f"Dashboard still live. Drive it yourself: cd {root} && nod task set DEMO-12 --status in_progress")
            print("Ctrl C to stop.")
            server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.terminate()


if __name__ == "__main__":
    main()
