# acquaint.resources

Files shipped inside the package: record templates, the policy tripwires, purpose reminders, the tells catalogue, skills.

Read through `importlib.resources` so they work from a wheel, a zip or a checkout.
Shipped data is part of the code: if it does not parse, that is a bug, and it raises.

### Functions

| [`data_path`](#acquaint.resources.data_path)(\*parts)   | A path inside `acquaint/data/`.                                           |
|-----------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`data_text`](#acquaint.resources.data_text)(name)      | The text of a shipped data file, e.g. `data_text("templates/POLICY.md")`. |
| [`data_yaml`](#acquaint.resources.data_yaml)(name)      | A shipped YAML file, parsed.                                              |

### acquaint.resources.data_path(\*parts)

A path inside `acquaint/data/`.

* **Return type:**
  [`Traversable`](https://docs.python.org/3/library/importlib.resources.abc.html#importlib.resources.abc.Traversable)

### acquaint.resources.data_text(name)

The text of a shipped data file, e.g. `data_text("templates/POLICY.md")`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### acquaint.resources.data_yaml(name)

A shipped YAML file, parsed. Raises `ValueError` if it does not parse.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
