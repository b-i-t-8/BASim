from models.parameters import get_simulation_parameters
import json

params = get_simulation_parameters()
all_params = params.get_all()

print(json.dumps(all_params, indent=2))
