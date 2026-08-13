import importlib.util
import importlib.machinery
import pathlib
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "sinetd"
LOADER = importlib.machinery.SourceFileLoader("sinetd", str(SCRIPT))
SPEC = importlib.util.spec_from_loader("sinetd", LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
import sys
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ConfigTests(unittest.TestCase):
    def test_parses_tcp_udp_and_src(self):
        rules, warnings = MODULE.parse_config_text(
            """
            logfile /var/log/rinetd.log
            0.0.0.0 8080 10.0.0.2 80
            0.0.0.0 5353/udp 10.0.0.53 53/udp
            192.0.2.10 8443 10.0.0.3 443 [src=10.0.0.1]
            """
        )
        self.assertEqual(3, len(rules))
        self.assertEqual("tcp", rules[0].protocol)
        self.assertEqual("udp", rules[1].protocol)
        self.assertEqual("10.0.0.1", rules[2].source_address)
        self.assertEqual(1, len(warnings))

    def test_target_protocol_inherits_listener(self):
        rules, _ = MODULE.parse_config_text("0.0.0.0 5353/udp 10.0.0.53 53")
        self.assertEqual("udp", rules[0].protocol)

    def test_rejects_duplicate_listener(self):
        with self.assertRaisesRegex(MODULE.ConfigError, "duplicate listener"):
            MODULE.parse_config_text(
                "0.0.0.0 8080 10.0.0.2 80\n0.0.0.0 8080 10.0.0.3 80"
            )

    def test_rejects_cross_protocol(self):
        with self.assertRaisesRegex(MODULE.ConfigError, "cannot translate"):
            MODULE.parse_config_text("0.0.0.0 5353/udp 10.0.0.53 53/tcp")

    def test_rejects_acl_directive(self):
        with self.assertRaisesRegex(MODULE.ConfigError, "ACLs are not supported"):
            MODULE.parse_config_text("allow 192.0.2.*\n0.0.0.0 80 10.0.0.2 80")

    def test_rendered_rules_are_scoped_to_owned_chains(self):
        rules, _ = MODULE.parse_config_text("0.0.0.0 8080 10.0.0.2 80")
        commands = MODULE.owned_rule_commands(rules, masquerade=True, local_output=False)
        joined = [" ".join(command) for _, command in commands]
        self.assertTrue(all("SINETD_" in command for command in joined))
        self.assertTrue(any("DNAT --to-destination 10.0.0.2:80" in command for command in joined))
        self.assertTrue(any("MASQUERADE" in command for command in joined))

    def test_no_masquerade_omits_snat_rule(self):
        rules, _ = MODULE.parse_config_text("0.0.0.0 8080 10.0.0.2 80")
        commands = MODULE.owned_rule_commands(rules, masquerade=False, local_output=False)
        self.assertFalse(any(chain == "nat" and "SINETD_SNAT" in args for chain, args in commands))

    def test_src_generates_fixed_snat(self):
        rules, _ = MODULE.parse_config_text(
            "0.0.0.0 8080 10.0.0.2 80 [src=10.0.0.1]"
        )
        commands = MODULE.owned_rule_commands(rules, masquerade=False, local_output=False)
        flat = [item for _, args in commands for item in args]
        self.assertIn("SNAT", flat)
        self.assertIn("10.0.0.1", flat)

    def test_local_output_is_opt_in(self):
        rules, _ = MODULE.parse_config_text("0.0.0.0 8080 10.0.0.2 80")
        disabled = MODULE.owned_rule_commands(rules, masquerade=True, local_output=False)
        enabled = MODULE.owned_rule_commands(rules, masquerade=True, local_output=True)
        self.assertFalse(any(MODULE.OUTPUT_CHAIN in args for _, args in disabled))
        self.assertTrue(any(MODULE.OUTPUT_CHAIN in args for _, args in enabled))

    def test_discovers_only_conf_files_in_sorted_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = pathlib.Path(temp_dir)
            (directory / "20-b.conf").write_text("# empty\n")
            (directory / "10-a.conf").write_text("# empty\n")
            (directory / "ignored.txt").write_text("# ignored\n")
            paths = MODULE.discover_config_paths([directory])
        self.assertEqual(["10-a.conf", "20-b.conf"], [path.name for path in paths])

    def test_combines_multiple_config_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = pathlib.Path(temp_dir)
            first = directory / "10-web.conf"
            second = directory / "20-dns.conf"
            first.write_text("0.0.0.0 8080 10.0.0.2 80\n")
            second.write_text("0.0.0.0 5353/udp 10.0.0.53 53\n")
            rules, _ = MODULE.parse_configs([first, second])
        self.assertEqual(2, len(rules))
        self.assertEqual({"tcp", "udp"}, {rule.protocol for rule in rules})

    def test_rejects_wildcard_and_specific_address_overlap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = pathlib.Path(temp_dir)
            first = directory / "10-wildcard.conf"
            second = directory / "20-specific.conf"
            first.write_text("0.0.0.0 8080 10.0.0.2 80\n")
            second.write_text("192.0.2.10 8080 10.0.0.3 80\n")
            with self.assertRaisesRegex(MODULE.ConfigError, "listener overlaps"):
                MODULE.parse_configs([first, second])


class FakeBackend:
    def __init__(self, fail_on_append=False):
        self.calls = []
        self.fail_on_append = fail_on_append
        self.restored = None

    def snapshot(self):
        self.calls.append(("snapshot",))
        return "saved rules"

    def restore(self, value):
        self.restored = value

    def ensure_chain(self, table, chain):
        self.calls.append(("ensure_chain", table, chain))

    def ensure_jump(self, table, builtin, chain):
        self.calls.append(("ensure_jump", table, builtin, chain))

    def remove_jump(self, table, builtin, chain):
        self.calls.append(("remove_jump", table, builtin, chain))

    def exec(self, table, args, check=True):
        self.calls.append(("exec", table, tuple(args)))
        if self.fail_on_append and args[0] == "-A":
            raise MODULE.CommandError(["iptables", *args], 1, "simulated")


class ApplyTests(unittest.TestCase):
    def test_apply_populates_owned_chains(self):
        rules, _ = MODULE.parse_config_text("0.0.0.0 8080 10.0.0.2 80")
        backend = FakeBackend()
        with (
            mock.patch.object(MODULE, "require_root"),
            mock.patch.object(MODULE, "require_programs"),
            mock.patch.object(MODULE, "enable_ip_forward", return_value="1"),
        ):
            MODULE.apply_rules(
                backend,
                rules,
                masquerade=True,
                local_output=False,
                allow_ip_forward_change=False,
            )
        appended = [call for call in backend.calls if call[0] == "exec" and call[2][0] == "-A"]
        self.assertEqual(4, len(appended))
        self.assertIsNone(backend.restored)

    def test_apply_restores_snapshot_on_failure(self):
        rules, _ = MODULE.parse_config_text("0.0.0.0 8080 10.0.0.2 80")
        backend = FakeBackend(fail_on_append=True)
        with (
            mock.patch.object(MODULE, "require_root"),
            mock.patch.object(MODULE, "require_programs"),
            mock.patch.object(MODULE, "enable_ip_forward", return_value="1"),
            self.assertRaises(MODULE.CommandError),
        ):
            MODULE.apply_rules(
                backend,
                rules,
                masquerade=True,
                local_output=False,
                allow_ip_forward_change=False,
            )
        self.assertEqual("saved rules", backend.restored)


if __name__ == "__main__":
    unittest.main()
