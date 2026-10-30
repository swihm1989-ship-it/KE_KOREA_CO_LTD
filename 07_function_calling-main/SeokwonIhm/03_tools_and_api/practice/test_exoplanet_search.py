import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

import exoplanet_search as app


class ExoplanetSearchTests(unittest.TestCase):
    def test_real_snapshot_search_and_truncation(self):
        result = app.search_exoplanets.invoke({
            "max_radius_earth": 2.0, "discovered_since": 2015, "limit": 3,
        })
        self.assertEqual(result.total_matches, 1267)
        self.assertEqual(result.returned_count, 3)
        self.assertEqual([p.name for p in result.planets],
                         ['Kepler-879 c', 'Kepler-444 b', 'Kepler-158 d'])
        self.assertTrue(all(p.radius_earth <= 2 and p.discovery_year >= 2015
                            for p in result.planets))
        radii = [p.radius_earth for p in result.planets]
        self.assertEqual(radii, sorted(radii))

    def test_defaults_and_method_filter(self):
        result = app.search_exoplanets.invoke({
            "max_radius_earth": 2, "discovery_method": "Transit",
        })
        self.assertEqual(result.returned_count, 5)
        self.assertTrue(all(p.discovery_method == "Transit" for p in result.planets))

    def test_empty_result_is_successful(self):
        result = app.search_exoplanets.invoke({"max_radius_earth": 0.01})
        self.assertEqual(result.model_dump(), {
            "total_matches": 0, "returned_count": 0, "planets": [],
        })

    def test_bad_inputs_are_rejected(self):
        for args in [{}, {"max_radius_earth": 0}, {"max_radius_earth": -1},
                     {"max_radius_earth": "2"}, {"max_radius_earth": float('nan')},
                     {"max_radius_earth": 2, "limit": 11},
                     {"max_radius_earth": 2, "discovered_since": 2027},
                     {"max_radius_earth": 2, "discovery_method": "magic"},
                     {"max_radius_earth": 2, "extra": True}]:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                app.search_exoplanets.invoke(args)

    def test_missing_file_is_failure_not_empty_result(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            with patch.object(app, 'PLANET_PATH', Path(folder) / 'missing.csv'):
                with self.assertRaises(FileNotFoundError):
                    app.search_exoplanets.invoke({"max_radius_earth": 2})

    def test_all_rows_are_validated_and_missing_radius_is_not_zero(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            path = Path(folder) / 'planets.csv'
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['pl_name', 'hostname', 'discoverymethod', 'disc_year', 'pl_rade'])
                writer.writerow(['Missing radius', 'Host', 'Transit', 2020, ''])
                writer.writerow(['Valid', 'Host', 'Transit', 2020, 2])
            with patch.object(app, 'PLANET_PATH', path):
                result = app.search_exoplanets.invoke({"max_radius_earth": 2})
                self.assertEqual([p.name for p in result.planets], ['Valid'])
                with path.open('a', encoding='utf-8', newline='') as stream:
                    csv.writer(stream).writerow(['Outside filter', 'Host', 'Transit', 'bad year', 50])
                with self.assertRaises(ValueError):
                    app.search_exoplanets.invoke({"max_radius_earth": 2})

    def test_result_counts_must_match(self):
        with self.assertRaises(ValidationError):
            app.PlanetResult(total_matches=1, returned_count=1, planets=[])


if __name__ == '__main__':
    unittest.main()
