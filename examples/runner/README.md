# Runner Flows

Flows of [Divengine Runner](https://github.com/divengine/runner) to try in divide.

```bash
composer install          # divengine/runner from Packagist, in vendor/
divide .
```

Open a Flow and press **Ctrl+F9** (Run > Run):

- `flows/hello.yml`: one Block, two Steps. Initial context `{"name": "Ana"}`, function root `functions`.
- `flows/order.yml`: `main` calls `review`, which calls `approval`, which pauses. Initial context `order.json`,
  function root `functions`. It pauses at `approval.ask` inside two calls; Ctrl+F9 again and **Resume** continues
  it from `flows/order.context.json`. `trail` in the context lists the Steps whose activities ran: none runs twice.
- `flows/invoice.yml`: the same function name (`total`) in two Modules, `billing` and `shipping`.

The same, without divide:

```bash
php vendor/divengine/runner/bin/run.php flows/order.yml --context order.json --root functions --save-context flows/order.context.json
php vendor/divengine/runner/bin/run.php flows/order.yml --context flows/order.context.json --save-context flows/order.context.json
```

Flows and their functions are trusted PHP code: Runner is not a sandbox.
