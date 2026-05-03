import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd


def validate_telemetry(data):
    """Validate one telemetry record with Great Expectations."""

    dataframe = pd.DataFrame([data])
    context = gx.get_context()
    data_source = context.data_sources.add_pandas(name="telemetry_data_source")
    batch = data_source.read_dataframe(dataframe)
    suite = build_telemetry_suite()
    validation_result = batch.validate(suite)

    if validation_result.success:
        return True, "Telemetry data is valid"

    # Collect failed checks so we can return the most useful one first.
    failed_results = [
        result for result in validation_result.results if not result.success
    ]

    # Show type problems before range problems because they are easier to debug.
    for result in failed_results:
        if result.expectation_config.type == "expect_column_values_to_be_of_type":
            column = result.expectation_config.kwargs.get("column", "table")
            return False, f"Validation failed for '{column}': expected correct type"

    for result in failed_results:
        column = result.expectation_config.kwargs.get("column", "table")
        return False, (
            f"Validation failed for '{column}': {result.expectation_config.type}"
        )

    return False, "Telemetry validation failed"


def build_telemetry_suite():
    """Build the expectation suite used for telemetry checks."""
    suite = gx.ExpectationSuite(name="telemetry_validation")

    # The telemetry message must have the exact required fields.
    suite.add_expectation(
        gxe.ExpectTableColumnsToMatchSet(
            column_set=[
                "node_id",
                "timestamp",
                "voltage",
                "current",
                "power",
                "energy_wh",
            ],
            exact_match=True,
        )
    )

    # node_id should be a text value.
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeOfType(
            column="node_id",
            type_="str",
        )
    )

    # timestamp should be an integer in epoch milliseconds.
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeOfType(
            column="timestamp",
            type_="int64",
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="timestamp",
            min_value=1000000000000,
            max_value=9999999999999,
        )
    )

    # Sensor values can be whole numbers or decimals.
    suite.add_expectation(
        gxe.ExpectColumnValuesToBeInTypeList(
            column="voltage",
            type_list=["int64", "float64"],
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="voltage",
            min_value=200,
            max_value=250,
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeInTypeList(
            column="current",
            type_list=["int64", "float64"],
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="current",
            min_value=0,
            strict_min=True,
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeInTypeList(
            column="power",
            type_list=["int64", "float64"],
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="power",
            min_value=0,
            strict_min=True,
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeInTypeList(
            column="energy_wh",
            type_list=["int64", "float64"],
        )
    )

    suite.add_expectation(
        gxe.ExpectColumnValuesToBeBetween(
            column="energy_wh",
            min_value=0,
        )
    )

    return suite


if __name__ == "__main__":
    sample_data = {
        "node_id": "node_1",
        "timestamp": 1700000000000,
        "voltage": 230.5,
        "current": 5.2,
        "power": 1196.6,
        "energy_wh": 5000.0,
    }

    is_valid, message = validate_telemetry(sample_data)
    print(is_valid, message)
