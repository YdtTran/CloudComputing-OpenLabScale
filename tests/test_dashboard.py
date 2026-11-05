"""Unit tests for the OpenLab-Scale Monitoring & License Dashboard."""
import json
import unittest
from dashboard.server import DashboardState, DashboardHandler


class DashboardStateTests(unittest.TestCase):
    def setUp(self):
        self.state = DashboardState(total_seats=3)
        self.state.sessions.clear()

    def test_checkout_and_pool_exhaustion(self):
        # 1. Checkout seat 1
        ok, res = self.state.checkout_license("s1", "Student 1", "MATLAB")
        self.assertTrue(ok)
        self.assertEqual(res["seat_id"], 1)

        # 2. Checkout seat 2 and 3
        ok, res = self.state.checkout_license("s2", "Student 2", "Cadence")
        self.assertTrue(ok)
        ok, res = self.state.checkout_license("s3", "Student 3", "Ansys")
        self.assertTrue(ok)

        # 3. 4th checkout must be rejected
        ok, res = self.state.checkout_license("s4", "Student 4", "SolidWorks")
        self.assertFalse(ok)
        self.assertEqual(res, "LICENSE_POOL_EXHAUSTED")

        status = self.state.get_status()
        self.assertEqual(status["license_pool"]["in_use"], 3)
        self.assertEqual(status["license_pool"]["free_seats"], 0)

    def test_reclaim_safety_blocks_active_and_degraded(self):
        self.state.checkout_license("s1", "Student 1", "MATLAB")
        # Default state is ACTIVE
        ok, err = self.state.approve_reclaim("s1")
        self.assertFalse(ok)
        self.assertIn("SAFETY_VIOLATION", err)

        # Degraded signal must block reclaim even if marked idle
        self.state.sessions["s1"]["status"] = "IDLE_CANDIDATE"
        self.state.sessions["s1"]["telemetry_status"] = "DEGRADED"
        ok, err = self.state.approve_reclaim("s1")
        self.assertFalse(ok)
        self.assertIn("DEGRADED", err)

    def test_reclaim_success_returns_seat_to_pool(self):
        self.state.checkout_license("s1", "Student 1", "MATLAB")
        self.state.sessions["s1"]["status"] = "IDLE_CANDIDATE"
        self.state.sessions["s1"]["telemetry_status"] = "OK"

        ok, res = self.state.approve_reclaim("s1")
        self.assertTrue(ok)
        self.assertEqual(res["returned_seat"], 1)

        # Seat 1 should now be available again
        ok, res2 = self.state.checkout_license("s2", "Student 2", "Cadence")
        self.assertTrue(ok)
        self.assertEqual(res2["seat_id"], 1)

    def test_telemetry_simulation_events(self):
        self.state.checkout_license("s1", "Student 1", "MATLAB")
        self.state.simulate_telemetry_event("s1", "burst")
        self.assertEqual(self.state.sessions["s1"]["status"], "ACTIVE")
        self.assertEqual(self.state.sessions["s1"]["idle_seconds"], 0)

        self.state.simulate_telemetry_event("s1", "idle_gap")
        self.assertEqual(self.state.sessions["s1"]["status"], "IDLE_CANDIDATE")
        self.assertEqual(self.state.sessions["s1"]["idle_seconds"], 40)


if __name__ == "__main__":
    unittest.main()
