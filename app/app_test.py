"""
Unit tests for Studio Batch Uploader backend helper functions.
Verifies ticket key parsing, project validation, and metadata mapping.
"""
import os
import unittest
import sys
from pathlib import Path

# Importar app en modo dev: evita el fail-closed de FLASK_SECRET_KEY al importar (C2).
os.environ.setdefault("FLASK_DEBUG", "True")

# Add app/ and reference/ directories to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reference"))

from app import safe_upload_filename, ticket_key_from_link
from studio_api import StudioAPIClient


class TestBatchUploaderHelpers(unittest.TestCase):
    def test_ticket_key_from_link_valid(self):
        """Verifies that valid SDS ticket keys and browse links are parsed correctly."""
        # Simple keys
        self.assertEqual(ticket_key_from_link("SDS-1234"), "SDS-1234")
        self.assertEqual(ticket_key_from_link("SDS-99999"), "SDS-99999")
        
        # Complete URL links
        self.assertEqual(
            ticket_key_from_link("https://seedtag.atlassian.net/browse/SDS-5678"),
            "SDS-5678"
        )
        # Extra spacing and text
        self.assertEqual(
            ticket_key_from_link("  Por favor revisar el ticket SDS-8212 urgente "),
            "SDS-8212"
        )

    def test_ticket_key_from_link_invalid(self):
        """Verifies that non-SDS keys or malformed strings are rejected."""
        # Other project keys
        self.assertIsNone(ticket_key_from_link("OTHER-1234"))
        self.assertIsNone(ticket_key_from_link("https://seedtag.atlassian.net/browse/PROJ-123"))
        
        # Malformed strings
        self.assertIsNone(ticket_key_from_link("SDS-"))
        self.assertIsNone(ticket_key_from_link("SDS1234"))
        self.assertIsNone(ticket_key_from_link("browse/SDS-"))
        self.assertIsNone(ticket_key_from_link(""))
        self.assertIsNone(ticket_key_from_link(None))

    def test_country_mapping(self):
        """Verifies that country codes map correctly to Studio country keys."""
        # Exact matches
        self.assertEqual(StudioAPIClient.map_country("us"), "usa")
        self.assertEqual(StudioAPIClient.map_country("usa"), "usa")
        self.assertEqual(StudioAPIClient.map_country("es"), "spain")
        self.assertEqual(StudioAPIClient.map_country("fr"), "france")
        self.assertEqual(StudioAPIClient.map_country("uk"), "uk")
        
        # Casings and spacing
        self.assertEqual(StudioAPIClient.map_country("  ES  "), "spain")
        self.assertEqual(StudioAPIClient.map_country("uS"), "usa")
        
        # Fallbacks for unknown countries
        self.assertEqual(StudioAPIClient.map_country("unknown"), "international")
        self.assertEqual(StudioAPIClient.map_country(None), "international")

    def test_category_mapping(self):
        """Verifies that industry strings map correctly to Studio categories."""
        # Exact matches
        self.assertEqual(StudioAPIClient.map_category("automotive"), "automotive")
        self.assertEqual(StudioAPIClient.map_category("beauty"), "beauty")
        self.assertEqual(StudioAPIClient.map_category("technology"), "technology")
        self.assertEqual(StudioAPIClient.map_category("tech"), "technology")
        
        # Complex multi-word fields
        self.assertEqual(
            StudioAPIClient.map_category("Business, Industry, And Logistics"),
            "industry"
        )
        self.assertEqual(
            StudioAPIClient.map_category("food and drinks"),
            "food-and-drinks"
        )
        
        # Non-matching inputs return None (does not throw)
        self.assertIsNone(StudioAPIClient.map_category("unknown_industry"))
        self.assertIsNone(StudioAPIClient.map_category(None))
        self.assertIsNone(StudioAPIClient.map_category(""))

    def test_safe_upload_filename(self):
        """Verifies that uploaded filenames stay local, safe, and unique."""
        used_names = set()

        self.assertEqual(
            safe_upload_filename("../../evil clip.mp4", used_names),
            "evil_clip.mp4"
        )
        self.assertEqual(
            safe_upload_filename("client spot.mp4", used_names),
            "client_spot.mp4"
        )
        self.assertEqual(
            safe_upload_filename("client spot.mp4", used_names),
            "client_spot_2.mp4"
        )
        self.assertEqual(safe_upload_filename("", used_names), "video")


if __name__ == "__main__":
    unittest.main()
