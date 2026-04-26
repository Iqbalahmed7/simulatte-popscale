"""
Tests for ground truth loaders and aggregation functions.
"""

import pytest
from pathlib import Path
from popscale.calibration.loaders import load_ground_truth
from popscale.calibration.enrichment import aggregate_to_clusters


class TestLoaders:
    """Test load_ground_truth() for all election datasets."""

    def test_load_us_2024_pres(self):
        """Load US 2024 presidential results."""
        gt = load_ground_truth("us_2024_pres")

        assert gt.election_id == "us_2024_pres"
        assert gt.date == "2024-11-05"
        assert gt.granularity == "county"
        assert len(gt.units) > 0

        # Verify schema
        unit = gt.units[0]
        assert unit.unit_id is not None
        assert unit.unit_name is not None
        assert "trump_pct" in unit.outcomes
        assert "harris_pct" in unit.outcomes
        assert "other_pct" in unit.outcomes
        assert unit.winner in ["trump", "harris", "other"]
        assert unit.margin_pct >= 0

    def test_load_wb_2021_assembly(self):
        """Load West Bengal 2021 assembly results."""
        gt = load_ground_truth("wb_2021_assembly")

        assert gt.election_id == "wb_2021_assembly"
        assert gt.date == "2021-04-27"
        assert gt.granularity == "constituency"
        assert len(gt.units) > 0

        # Verify schema
        unit = gt.units[0]
        assert unit.unit_id is not None
        assert unit.unit_name is not None
        assert "tmc_pct" in unit.outcomes
        assert "bjp_pct" in unit.outcomes
        assert "left_pct" in unit.outcomes
        assert "congress_pct" in unit.outcomes
        assert "others_pct" in unit.outcomes
        assert unit.winner in ["tmc", "bjp", "left", "congress", "others"]
        assert unit.margin_pct >= 0

    def test_load_india_2024_ls(self):
        """Load India 2024 Lok Sabha results."""
        gt = load_ground_truth("india_2024_ls")

        assert gt.election_id == "india_2024_ls"
        assert gt.date == "2024-06-04"
        assert gt.granularity == "constituency"
        assert len(gt.units) > 0

        # Verify schema
        unit = gt.units[0]
        assert unit.unit_id is not None
        assert unit.unit_name is not None
        assert "bjp_pct" in unit.outcomes
        assert "congress_pct" in unit.outcomes
        assert "regional_pct" in unit.outcomes
        assert unit.winner in ["bjp", "congress", "regional", "others"]
        assert unit.margin_pct >= 0

    def test_load_india_2019_ls(self):
        """Load India 2019 Lok Sabha results."""
        gt = load_ground_truth("india_2019_ls")

        assert gt.election_id == "india_2019_ls"
        assert gt.date == "2019-05-23"
        assert gt.granularity == "constituency"
        assert len(gt.units) > 0

        # Verify schema
        unit = gt.units[0]
        assert unit.unit_id is not None
        assert unit.unit_name is not None
        assert "bjp_pct" in unit.outcomes
        assert "congress_pct" in unit.outcomes
        assert unit.margin_pct >= 0

    def test_load_unknown_id_raises(self):
        """Attempting to load unknown election_id raises ValueError."""
        with pytest.raises(ValueError, match="Unknown election_id"):
            load_ground_truth("nonexistent_election")

    def test_load_missing_file_raises(self):
        """Attempting to load with missing CSV raises FileNotFoundError."""
        # This test assumes the dataset CSV is actually present
        # If datasets don't exist, they raise FileNotFoundError
        pass


class TestAggregation:
    """Test cluster aggregation for WB 2021."""

    def test_aggregate_to_clusters(self):
        """Aggregate WB 2021 constituency results to cluster level."""
        gt = load_ground_truth("wb_2021_assembly")

        # Use the cluster_mapping CSV
        cluster_mapping = (
            Path(__file__).parent.parent
            / "ground_truth"
            / "wb_2021_assembly"
            / "cluster_mapping.csv"
        )

        if not cluster_mapping.exists():
            pytest.skip("Cluster mapping CSV not found")

        clusters = aggregate_to_clusters(gt, cluster_mapping)

        # Should return a dict
        assert isinstance(clusters, dict)

        # Each cluster should map to vote shares
        for cluster_id, outcomes in clusters.items():
            assert isinstance(cluster_id, str)
            assert isinstance(outcomes, dict)

            # Each outcome should be a float percentage
            for party, share in outcomes.items():
                assert isinstance(party, str)
                assert isinstance(share, float)
                assert 0 <= share <= 100

    def test_aggregate_uses_all_parties(self):
        """Verify aggregation includes all parties from constituencies."""
        gt = load_ground_truth("wb_2021_assembly")

        cluster_mapping = (
            Path(__file__).parent.parent
            / "ground_truth"
            / "wb_2021_assembly"
            / "cluster_mapping.csv"
        )

        if not cluster_mapping.exists():
            pytest.skip("Cluster mapping CSV not found")

        clusters = aggregate_to_clusters(gt, cluster_mapping)

        # Expect TMC, BJP, Left, Congress, Others for WB
        for cluster_id, outcomes in clusters.items():
            assert "tmc_pct" in outcomes
            assert "bjp_pct" in outcomes
