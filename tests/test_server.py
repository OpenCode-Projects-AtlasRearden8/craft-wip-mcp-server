"""Server-dispatch tests: runs handler in-process (offline, no stdio needed)."""

import json
import unittest

import server


class InProcessServer:
    """Wraps a Server writing to a private temp data file."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from pathlib import Path

        cls._tmp = Path(tempfile.mkdtemp(prefix="craftsrv-")).resolve()
        cls.data_file = cls._tmp / "craft-store.json"
        cls.server_obj = server.Server(data_file=cls.data_file, seed=True)

    def call_tool(self, name, args=None):
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        }
        resp = server.handle_message(msg, self.server_obj)
        self.assertIn("result", resp)
        self.assertFalse(resp["result"].get("isError"), resp["result"]["content"][0]["text"])
        payload = resp["result"]["content"][0]["text"]
        if isinstance(payload, str) and payload.lstrip().startswith(("{", "[")):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                pass
        return payload

    def call_tool_expect_tool_error(self, name, args=None):
        resp = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": name, "arguments": args or {}}},
            self.server_obj,
        )
        return resp["result"]


class TestProtocol(unittest.TestCase):
    def test_initialize_handshake(self):
        resp = server.handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize"}, None)
        self.assertEqual(resp["result"]["serverInfo"]["name"], "craft-wip-mcp-server")

    def test_tools_list_shape(self):
        resp = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None)
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertTrue({"add_wip", "update_progress", "finish_first", "add_gift_deadline"} <= names)

    def test_notification_gets_no_response(self):
        self.assertIsNone(
            server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, None)
        )

    def test_unknown_method(self):
        resp = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "wat/wat"}, None)
        self.assertIn("error", resp)

    def test_unknown_tool(self):
        resp = server.handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}}, None
        )
        self.assertIn("error", resp)

    def test_bad_json_input_is_rejected_protocol_error(self):
        resp = server.handle_message("just a string", None)
        self.assertIn("error", resp)


class TestTools(unittest.TestCase, InProcessServer):
    @classmethod
    def setUpClass(cls):
        InProcessServer.setUpClass()

    def test_sample_store_seeded(self):
        wips = self.call_tool("list_wips")
        self.assertGreaterEqual(len(wips), 3)
        self.assertTrue(any(w["id"] == "w-1" for w in wips))
        self.assertTrue(any(w["name"] == "Cranberry cable scarf" for w in wips))

    def test_update_progress_and_use_stash(self):
        self.call_tool("log_stash", {"material": "Craft glue", "quantity": 2, "unit": "bottles"})
        item = self.call_tool("use_stash", {"material": "craft glue", "quantity": 1})
        self.assertEqual(item["quantity"], 1)
        progress = self.call_tool("update_progress", {"wip_id": "w-3", "add_units": 1})
        self.assertEqual(progress["progress_pct"], 100)

    def test_add_wip_and_finish_first(self):
        made = self.call_tool(
            "add_wip",
            {
                "name": "Chess-piece coasters",
                "craft_type": "resin",
                "pattern_notes": "Resin mold, knight first.",
                "total_units": 8,
                "done_units": 4,
            },
        )
        self.assertEqual(made["done_units"], 4)
        ranked = self.call_tool("finish_first", {"limit": 2})
        top = ranked["what_to_pick_up_next"][0]
        self.assertIn("name", top)
        self.assertIn("score", top)

    def test_deadline_add_and_nudge(self):
        self.call_tool("add_gift_deadline", {
            "wip_id": "w-2",
            "recipient": "Niece Rori",
            "event_date": "2026-11-28",
            "lead_time_days": 30,
        })
        rows = self.call_tool("list_deadlines")
        self.assertTrue(any(r["recipient"] == "Niece Rori" for r in rows))
        self.assertIn("days_left", rows[0])

    def test_tool_errors_surface_iserror_false_upstream_so_expect_true(self):
        result = self.call_tool_expect_tool_error(
            "update_progress", {"wip_id": "w-does-not-exist", "add_units": 1}
        )
        self.assertTrue(result["isError"])
        self.assertIn("no wip", result["content"][0]["text"])

    def test_overfull_progress_rejected(self):
        result = self.call_tool_expect_tool_error(
            "update_progress", {"wip_id": "w-1", "add_units": 999}
        )
        self.assertTrue(result["isError"])

    def test_use_stash_more_than_owned_rejected(self):
        result = self.call_tool_expect_tool_error(
            "use_stash", {"material": "merino worsted - cranberry", "quantity": 10_000}
        )
        self.assertTrue(result["isError"])

    def test_nonfinite_and_giant_quantities_rejected(self):
        for arg in ({"quantity": 10**12}, {"quantity": -5}, {"quantity": 0}):
            result = self.call_tool_expect_tool_error("log_stash", {"material": "felt", **arg})
            self.assertTrue(result["isError"], str(arg))

    def test_injection_style_names_are_stored_as_data(self):
        odd = "kraken'); DROP TABLE stash;--"
        self.call_tool("log_stash", {"material": odd, "quantity": 1, "unit": "spool"})
        matches = [s for s in self.call_tool("list_stash") if "kraken" in s["material"]]
        self.assertEqual(len(matches), 1)

    def test_backup_written_on_mutation(self):
        self.call_tool("log_stash", {"material": "backup probe felting wool", "quantity": 3, "unit": "grams"})
        backups = (self.data_file.parent / "backups").glob("craft-store-*.json")
        self.assertGreaterEqual(len(list(backups)), 1)

    def test_data_file_stays_next_to_its_dir(self):
        self.assertEqual(self.data_file.parent, self._tmp)


if __name__ == "__main__":
    unittest.main()
