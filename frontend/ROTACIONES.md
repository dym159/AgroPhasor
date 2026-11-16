# Rotations in the UI

With a parcel selected, the panel waits until the user picks a strategy, adjusts a priority knob, or selects a crop. It then queries `POST /api/v1/parcelas/rotaciones` with the reference profile and displays the suggested sequence (three periods by default, configurable up to six). It uses the first calendar date and the backend identifies the parcel's region. With a single crop selected, it pins that crop at the start and searches for compatible partners. With multiple crops selected, it searches among them. With no crop selected, it searches across the available catalog.

If the backend cannot identify a department/region, the panel prompts the user to select one before displaying a sequence. Varieties with documented regional coverage participate only in their registered regions.

Strategy presets update the priority knobs. Once a Pareto result is loaded, changing knob weights selects an alternative sequence locally without re-querying. Changing the parcel geometry, selected crops, or rotation length triggers a fresh backend evaluation.

Recommendations use historical NASA POWER climate. Soil, management, and economic parameters from the catalog act as reference defaults. The detailed contract remains available for integrations supplying parcel-specific data.

UI tests: `npm test`.
