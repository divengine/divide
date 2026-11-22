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
  it from `.div/runner/flows/order.yml.context.json`, divide's checkpoint for that Flow (`.div/runner/` is kept out of Git). `trail` in the context lists the Steps whose activities ran: none runs twice.
- `flows/invoice.yml`: the same function name (`total`) in two Modules, `billing` and `shipping`.
- `flows/fulfil.yml`: four Blocks, calls between them and a jump that retries a Step once (`stock.short` jumps back
  to `.reserve`). Initial context `order.json`, function root `functions`. Run > Flow designer draws it as a board.

The same, without divide:

```bash
mkdir -p .div/runner/flows    # Runner writes into a folder that exists
php vendor/divengine/runner/bin/run.php flows/order.yml --context order.json --root functions --save-context .div/runner/flows/order.yml.context.json
php vendor/divengine/runner/bin/run.php flows/order.yml --context .div/runner/flows/order.yml.context.json --save-context .div/runner/flows/order.yml.context.json
```

Flows and their functions are trusted PHP code: Runner is not a sandbox.
