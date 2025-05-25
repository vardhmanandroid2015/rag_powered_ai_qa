# rag_app/services/time_series_handler.py

import re
from datetime import datetime, timedelta, UTC
from dateutil import parser as date_parser # For more flexible date parsing
import os
from dotenv import load_dotenv

# Import the executor and formatter functions from the previous part
from services.influxdb_executor import execute_flux_query, format_flux_tables_for_llm

# Import configuration - needed for bucket names in Flux queries
try:
    from config import (
        INFLUXDB_BUCKET, # Assuming this is the default bucket for metrics
        # If you have a separate alerts bucket, add it here, e.g.:
        # ALERTS_BUCKET = os.environ.get("ALERTS_BUCKET", "alerts")
    )
except ImportError:
    print("❌ Could not import InfluxDB configuration from config.py.")
    print("   Ensure config.py exists and defines INFLUXDB_BUCKET.")
    # Provide default values if config.py fails to import, for standalone testing capability
    INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "system_services") # Default if config fails


# --- Define Known AIOps Elements for Rule-Based Parsing ---
# These dictionaries map keywords found in natural language queries
# to the actual measurement names, field names, or tag values in InfluxDB.
# This is a basic, rule-based approach. A real system would need NLU or an LLM for this.

# Mapping keywords to InfluxDB measurement names or specific fields/measurements
KNOWN_METRICS_AND_MEASUREMENTS = {
    "latency": {"measurement": "api_latency", "field": "value"}, # Map 'latency' to api_latency measurement and value field
    "api latency": {"measurement": "api_latency", "field": "value"}, # Synonym
    "cpu": {"measurement": "docker_container_stats", "field": "cpu_usage_total"}, # Map 'cpu' to docker stats measurement and CPU field
    "memory": {"measurement": "docker_container_stats", "field": "memory_usage_bytes"}, # Map 'memory' to docker stats measurement and Memory field
    "usage": {"measurement": "docker_container_stats", "field": "cpu_usage_total"}, # Default generic 'usage' to CPU
    "utilization": {"measurement": "docker_container_stats", "field": "cpu_usage_total"}, # Map 'utilization' to CPU
    "errors": {"measurement": "error_logs", "field": "error_count"}, # Example mapping for log metrics
    "error rate": {"measurement": "error_logs", "field": "error_count"},
    "alerts": {"measurement": "alerts", "field": "alert_name"}, # Map 'alerts' to an alerts measurement and alert_name field
    "performance": ["api_latency", "docker_container_stats"], # Generic term might map to multiple sources
}

# Mapping keywords to InfluxDB tag values (e.g., service names, container names)
KNOWN_ENTITIES = {
    "payment service": {"tag": "service", "value": "payment"}, # Map keyword phrase to service tag value
    "payment": {"tag": "service", "value": "payment"}, # Map keyword to service tag value
    "user service": {"tag": "service", "value": "user"},
    "user": {"tag": "service", "value": "user"},
    "auth service": {"tag": "service", "value": "auth"},
    "auth": {"tag": "service", "value": "auth"},
    # Add specific container name mappings if they aren't covered by generic entity keywords
    "rag_app_web": {"tag": "container_name", "value": "mongodb"},
    "rag_app_db_pg": {"tag": "container_name", "value": "postgres"},
    # Add more entity mappings as needed
}

# Generic keywords that might indicate an entity without a specific name
GENERIC_ENTITY_KEYWORDS = ["container", "service", "host", "server"]


# --- Time Range Parsing ---
def parse_time_range(query_text: str):
    """
    Attempts to parse a relative time range from the query text.
    Returns a Flux duration string (e.g., "-1h", "-5m") or None.
    Uses regex and dateutil for flexibility.
    """
    query_lower = query_text.lower()

    # Look for simple relative time phrases like "last X minutes/hours/days"
    match_last = re.search(r"last (\d+)\s*(minute|minutes|hour|hours|day|days)", query_lower)
    if match_last:
        value = int(match_last.group(1))
        unit = match_last.group(2)
        if 'minute' in unit:
            return f"-{value}m"
        elif 'hour' in unit:
             return f"-{value}h"
        elif 'day' in unit:
             return f"-{value}d"

    # Could add support for other phrases like "today", "yesterday", "this week"
    # Or absolute timestamps using date_parser, but this adds significant complexity.

    # Default to last hour if no clear time range is specified
    print("⚠️ No specific time range found in query, defaulting to last hour (-1h).")
    return "-1h"


# --- Flux Query Builder - ADAPTED for AIOps scenarios ---
def build_flux_query_from_natural_language(user_query: str, time_range_flux: str):
    """
    Attempts to build a Flux query based on detected entities, metrics, and time range.
    Handles specific AIOps query patterns (api_latency, docker_stats, alerts).
    Returns the Flux query string or None if a query cannot be built.
    """
    query_lower = user_query.lower()

    # 1. Identify Potential Metrics/Measurements
    identified_metrics_info = set()
    for keyword, info in KNOWN_METRICS_AND_MEASUREMENTS.items():
        if keyword in query_lower:
            if isinstance(info, list): # Handle generic keywords mapping to multiple sources
                 for item in info:
                      # Need a way to get metric/field for generic terms, maybe default?
                      # For simplicity, let's skip generic terms for now and require specific metric words.
                      # Or refine KNOWN_METRICS_AND_MEASUREMENTS to map generics to default fields/measurements.
                      pass # Skip complex generic handling in this basic version
            else:
                 identified_metrics_info.add(tuple(info.items())) # Store as tuples for hashability

    # Convert set of tuples back to a list of dicts for easier processing
    identified_metrics_info = [dict(item) for item in identified_metrics_info]


    # 2. Identify Potential Entities (Services or Container Names)
    identified_entities_info = {tuple(info.items()) for keyword, info in KNOWN_ENTITIES.items() if keyword in query_lower}
    identified_entities_info = [dict(item) for item in identified_entities_info]

    # Basic fallback: if no specific entity keyword matched, check for generic ones + surrounding words
    # This is very fragile and likely needs replacement with NLU/LLM entity extraction
    if not identified_entities_info and any(keyword in query_lower for keyword in GENERIC_ENTITY_KEYWORDS):
        # Try to extract a word after a generic keyword as a potential entity name
        match = re.search(r"(?:container|service|host|server)\s+['\"]?([^'\"]+)['\"]?", query_lower)
        if match:
            # We don't know *what* tag this is for sure, assume container_name for docker stats
            # or service for general cases. This needs refinement.
            # Let's just add it as a generic "entity_name" to filter on later
            # This will only work if the tag key in InfluxDB matches the entity type keyword used
             potential_entity_name = match.group(1)
             if "container" in match.group(0):
                 identified_entities_info.append({"tag": "container_name", "value": potential_entity_name})
             elif "service" in match.group(0):
                  identified_entities_info.append({"tag": "service", "value": potential_entity_name})
             # Add other entity types here
             print(f"Attempted to identify potential entity name: {potential_entity_name}")


    # 3. Identify Conditions/Aggregations/Query Type
    detected_condition = None
    if "spike" in query_lower or "high" in query_lower or "peak" in query_lower:
        detected_condition = "spike" # Flag for LLM interpretation or specific Flux logic
    elif "average" in query_lower or "mean" in query_lower:
        detected_condition = "mean" # Can implement this in Flux
    elif "highest" in query_lower or "maximum" in query_lower:
        detected_condition = "max" # Can implement this in Flux
    elif "lowest" in query_lower or "minimum" in query_lower:
        detected_condition = "min" # Can implement this in Flux
    elif "count" in query_lower or "number of" in query_lower:
         detected_condition = "count" # Can implement this in Flux (e.g., count errors)

    # Explicit check for alerts query
    is_alerts_query = "alert" in query_lower or "alerts" in query_lower


    # --- Build Query Based on Identified Elements ---
    # We need to select the correct measurement and apply the right filters based on the query intention.

    # Case 1: Query about Alerts
    if is_alerts_query:
        # Query the alerts measurement
        query = f'''
from(bucket: "{INFLUXDB_BUCKET}") // **UPDATE: Use your actual alerts bucket name if different from INFLUXDB_BUCKET**
  |> range(start: {time_range_flux})
  |> filter(fn: (r) => r["_measurement"] == "alerts")
  |> filter(fn: (r) => r["_field"] == "alert_name") // Assuming alert name is in this field

'''
        # Add filters based on identified entities (service or container) if needed for alerts
        if identified_entities_info:
             entity_filters = " or ".join([f'r["{e["tag"]}"] == "{e["value"]}"' for e in identified_entities_info if "tag" in e and "value" in e])
             if entity_filters:
                 query += f'  |> filter(fn: (r) => {entity_filters})\n'

        # Filter for firing alerts if keywords like "firing" or "active" are used (optional refinement)
        # if "firing" in query_lower or "active" in query_lower:
        #      query += '  |> filter(fn: (r) => r["status"] == "firing")\n' # Assuming 'status' tag

        # Decide what to yield: list of alert names? count?
        # Let's yield distinct alert names for now
        query += '  |> distinct(column: "_value")\n'
        query += '  |> sort(columns: ["_time"], desc: true)\n' # Sort by time descending

        print(f"Built Flux query for alerts: {query}")
        return query


    # Case 2: Query about API Latency (targeting 'api_latency' measurement)
    # Check if 'api_latency' metric info was identified
    api_latency_metric_info = next((item for item in identified_metrics_info if item.get("measurement") == "api_latency"), None)

    if api_latency_metric_info and identified_entities_info: # API Latency usually tied to a service/endpoint
         # Find entity info specifically for 'service' tag
         service_entity_info = next((item for item in identified_entities_info if item.get("tag") == "service"), None)

         if service_entity_info:
             query = f'''
from(bucket: "{INFLUXDB_BUCKET}") // **UPDATE: Use your actual API metrics bucket name if different**
  |> range(start: {time_range_flux})
  |> filter(fn: (r) => r["_measurement"] == "{api_latency_metric_info['measurement']}")
  |> filter(fn: (r) => r["_field"] == "{api_latency_metric_info['field']}") // Should be 'value' for latency
  |> filter(fn: (r) => r["service"] == "{service_entity_info['value']}")
'''
             # Add endpoint filter if identified (need to add endpoint to KNOWN_ENTITIES or parse it)
             # For simplicity, skipping endpoint filter unless explicitly parsed.

             # Apply aggregation if requested (only mean, max, min for simplicity)
             if detected_condition in ["mean", "max", "min"]:
                  # Aggregate window needs to be appropriate - e.g., 1 minute
                  query += f'  |> aggregateWindow(every: 1m, fn: {detected_condition}, createEmpty: false)\n'
                  query += '  |> group(columns: ["service", "_field"])\n' # Group by service and field

             # Add sorting
             query += '|> sort(columns: ["_time"], desc: false)\n' # Ascending time sort

             # Yield the results
             yield_name = f"{detected_condition}_payment_latency" if detected_condition else "payment_latency_data"
             query += f'  |> yield(name: "{yield_name}")\n'


             print(f"Built Flux query for API Latency: {query}")
             return query
         else:
              print("Could not identify a specific service for the API latency query.")
              # Maybe return a query for all api_latency by measurement+field? Needs careful handling.
              return None # Cannot build specific query

    # Case 3: Query about Docker Container Stats (targeting 'docker_container_stats' measurement)
    # Check if Docker stats metrics info was identified
    docker_stats_metrics_info = [item for item in identified_metrics_info if item.get("measurement") == "docker_container_stats"]

    if docker_stats_metrics_info and identified_entities_info: # Docker stats tied to containers
         # Find entity info specifically for 'container_name' tag
         container_entity_info = next((item for item in identified_entities_info if item.get("tag") == "container_name"), None)

         if container_entity_info:
              field_filters = " or ".join([f'r["_field"] == "{m["field"]}"' for m in docker_stats_metrics_info])
              query = f'''
from(bucket: "{INFLUXDB_BUCKET}") // **UPDATE: Use your actual Docker stats bucket name if different**
  |> range(start: {time_range_flux})
  |> filter(fn: (r) => r["_measurement"] == "docker_container_stats")
  |> filter(fn: (r) => {field_filters})
  |> filter(fn: (r) => r["container_name"] == "{container_entity_info['value']}")
'''
              # Apply aggregation if requested
              if detected_condition in ["mean", "max", "min"]:
                   query += f'  |> aggregateWindow(every: 1m, fn: {detected_condition}, createEmpty: false)\n'
                   query += '  |> group(columns: ["container_name", "_field"])\n' # Group by container and field

              # Add sorting
              query += '|> sort(columns: ["_time"], desc: false)\n'

              # Yield the results
              yield_name = f"{detected_condition}_{container_entity_info['value']}_stats" if detected_condition else f"{container_entity_info['value']}_stats_data"
              query += f'  |> yield(name: "{yield_name}")\n'

              print(f"Built Flux query for Docker Stats: {query}")
              return query
         else:
              print("Could not identify a specific container name for the Docker stats query.")
              return None # Cannot build specific query


    # If none of the specific AIOps cases matched
    print("Could not build a specific AIOps Flux query.")
    return None


def handle_time_series_query(user_query: str):
    """
    Main function to process time-series related questions (API Latency, Docker Stats, Alerts).
    Orchestrates parsing, query building, execution, and formatting.
    Returns formatted results for LLM (string) and a boolean flag (True if query executed without fundamental error, even if no data).
    """
    print(f"Attempting to handle time-series query: {user_query}")

    # 1. Parse Time Range
    time_range_flux = parse_time_range(user_query)
    # time_range_flux will have a default like "-1h" if not parsed


    # 2. Build InfluxDB Query (for relevant AIOps data)
    # This single function now tries to build a query for any *known* AIOps pattern
    influx_query = build_flux_query_from_natural_language(user_query, time_range_flux)

    if influx_query is None:
        print("Could not build a specific InfluxDB query from the user query for AIOps.")
        # Return a message indicating failure to build query, False flag
        return "Could not determine relevant metrics, entities, or query type to search time-series database for AIOps data.", False


    # 3. Execute InfluxDB Query
    # execute_flux_query handles client initialization, health check retries, execution, and closing.
    query_results_tables = execute_flux_query(influx_query)

    if query_results_tables is None: # Check if execute_flux_query returned None due to error/failure
         # The executor already printed the error details.
         # Return a generic error message for the user/LLM, False flag
         return "An error occurred while querying the time-series database.", False

    if not query_results_tables or all(not table.records for table in query_results_tables):
         # Query executed successfully, but returned no data.
         print("InfluxDB query returned no data for AIOps.")
         # Indicate no data was found, but the query attempt was made and successful execution-wise
         # Return a specific message for the LLM, True flag (as query executed successfully)
         return "Query found relevant parameters, but no time-series data was retrieved for that period.", True # Return True because query executed

    # 4. Process and Format Results for LLM
    # TODO: More advanced analysis (like spike detection based on data values) could happen here
    # if detected_condition == "spike". For now, format the data and let LLM interpret.
    formatted_results_for_llm = format_flux_tables_for_llm(query_results_tables)
    print(f"Formatted InfluxDB AIOps results:\n{formatted_results_for_llm}")

    # Return formatted string and indicate TS data was retrieved (True flag)
    return formatted_results_for_llm, True


# --- Query Routing Heuristic ---
# This function decides IF handle_time_series_query should be called.
def is_aiops_time_series_query(query_text: str) -> bool:
    """
    Basic heuristic to detect if a query is likely asking about AIOps time-series data.
    Checks for combinations of keywords related to metrics, entities, and time.
    Needs improvement (e.g., using an LLM classifier).
    """
    query_lower = query_text.lower()

    # Keywords related to metrics, monitoring, events
    metric_keywords = ["latency", "cpu", "memory", "error", "log", "alert", "spike", "usage", "utilization", "performance", "monitor", "status", "metrics", "event", "errors"]
    # Keywords related to entities being monitored
    entity_keywords = ["docker", "container", "containers", "host", "server", "service"] + list(KNOWN_ENTITIES.keys())
     # Phrases indicating a time range
    time_phrases = ["last hour", "last minute", "in the last", "past hour", "past minute", "recently", "over time", "between", "from", "to"]

    # A query is likely AIOps TS if it contains:
    # (metrics keywords OR alert keywords) AND (entity keywords OR specific entity names) AND time phrases
    # Let's use a slightly more flexible check: Needs a metric/alert OR an entity keyword, PLUS a time phrase.
    has_metric_or_alert = any(keyword in query_lower for keyword in metric_keywords) or "alert" in query_lower or "alerts" in query_lower
    has_time_phrase = any(phrase in query_lower for phrase in time_phrases)
    has_entity_ref = any(keyword in query_lower for keyword in entity_keywords)


    # Consider it an AIOps query if it mentions metrics/alerts OR entities AND a time phrase.
    # Or if it explicitly asks about alerts.
    if (has_metric_or_alert or has_entity_ref) and has_time_phrase:
        return True

    # Also explicitly consider queries mentioning specific known entities + metrics, even if time phrase is weak
    if has_metric_or_alert and any(entity in query_lower for entity in [info["value"].lower() for info in KNOWN_ENTITIES.values()]):
         # If a specific metric/alert is mentioned AND a specific known service/container name
         return True

    # Add a check for just 'alerts' if it's often used without other keywords
    if "alert" in query_lower or "alerts" in query_lower:
        return True


    return False


# --- Example Usage (for testing this script directly) ---
# This block allows you to run this file independently to test the query detection and handling logic.
if __name__ == "__main__":
    print("--- Running time_series_handler.py standalone test ---")

    # Load env vars again just in case for standalone run
    load_dotenv()
    try:
        from config import (
            INFLUXDB_URL,
            INFLUXDB_TOKEN,
            INFLUXDB_ORG,
            INFLUXDB_BUCKET,  # Use the primary bucket from config
        )
    except ImportError:
        print("❌ Could not import InfluxDB configuration from config.py.")
        print("   Ensure config.py exists and defines INFLUXDB_URL, TOKEN, ORG, BUCKET.")
        # Provide default values if config.py fails to import, for standalone testing capability
        INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
        INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN")
        INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG")
        INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "system_services")
    # Note: influxdb_executor also loads dotenv, but doing it here ensures
    # the handler's own config imports work if run directly.


    # --- Define Example User Queries ---
        # "Are there any alerts for the payment service in the last day?", # Alerts query
        # "Tell me about the performance of the payment service in the last hour", # Generic performance, needs interpretation
        # "Show me error counts for the user service recently", # Log metrics example
    # Test queries related to the AIOps use case
    queries = [
        "What was the API latency for the payment service in the last 5 minutes?", # Specific latency, service, time
        "Was there a spike in API latency for payment in the last hour?", # Spike interpretation needed by LLM
        "Show me the average API latency for the payment service recently?", # Aggregation (mean)
        "Show me the highest CPU usage for mongodb container in the last hour.", # Docker stats, specific container
        "What was the memory usage for the postgres last 30 minutes?", # Docker stats (potentially, depends if user service is a container)
        "What are the differences between SQL and NoSQL databases?", # Non-AIOps query - should NOT trigger TS handler
        "Upload a PDF", # Non-AIOps query
    ]

    for query in queries:
        print(f"\n--- Processing User Query: '{query}' ---")
        # First, check if it's an AIOps time-series query using the heuristic
        if is_aiops_time_series_query(query):
             print(">> Query DETECTED as potential AIOps time-series query.")
             # Call the handler function
             formatted_ts_data, data_retrieved = handle_time_series_query(query)

             if data_retrieved: # True means query executed successfully (even if no data found)
                 print("\n>> Handler executed successfully. Formatted TS Data:")
                 print(formatted_ts_data) # This contains the data or a "no data found" message
             else: # False means a fundamental error occurred during query building or execution
                 print(f"\n>> Handler FAILED or could not build query: {formatted_ts_data}")

        else:
             print(">> Query NOT detected as AIOps time-series query.")
             # In the main app, this would fall back to standard RAG
             print("(Would proceed with standard RAG retrieval)")

        print("----------------------------------------------------")