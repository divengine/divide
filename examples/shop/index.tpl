<!--{
    @name Storefront
    @description Home page of the demo shop
}-->
{= year: 2026 =}
{% layout/header %}
<main>
  <h1>{^^title}</h1>
  <p>{$tagline}</p>
  <section class="products">
  [$products] product =>
    {% components/card %}
  @empty@
    <p>Nothing on sale today.</p>
  [/$products]
  </section>
  {?( {$cart.items} > 0 )?}
  <a href="/cart">Cart: {$cart.items} items</a>
  {/?}
</main>
{% layout/footer %}
