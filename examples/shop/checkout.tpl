{% layout/header %}
<h1>Checkout</h1>
[$cart.lines]
  <li>{$name} x {$qty}</li>
{?( {$cart.total} > 100 )?}
  <p>Free shipping!</p>
{% components/coupon %}
{= shipping: {"zone": "EU", "days": } =}
[/$orders]
{% layout/footer %}
