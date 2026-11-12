<!--{
    @name Showcase
    @description Every Div construct, for the highlighter
    @vars: required string title
}-->
{= title: "mozilla firefox" =}
{= *locked: "protected value" =}
{= product: { name: "Potato", price: 45, tags: ["a", "b"], ok: true } =}
{= digits: [[:0,8:]{$value},[/]9] =}
{= total: ->sum(20,30) =}
{= copy: $title =}
{@ [false, "NO"] @}
{% layout %}
{%% components/card %%}
<html>
  <body class="page {$theme}" data-id='{$id}'>
    <h1>{^^title} &amp; {$title|0,3|_|^|}</h1>
    <p>{$body:~25} {$body:/30} {$body:0,11} {$value:%1$04d}</p>
    <p>{html:body} {json:product} {js:title} {upper:title} {&url} {%%body}</p>
    <time>{/div.now:Y-m-d/}</time> <b>{#price:2,.#}</b>
    Sum: (# {$a} + {$b} * 2 :2. #) Min: {$min:blocks-weight} Count: {$items}
    Hello{\n}World{\t}{\$}
    [$products] product =>
      <li>{$_order}. {$product.name}{?( {$_index} == 3 )?} @break@ {/?}</li>
      !$_is_last, $_is_last!
    @empty@
      <li>No products</li>
    [/$products]
    [:1,10,x,2:] {$x} [/]
    ?$user.logged
      Welcome {$user.name}
    @else@
      Please log in
    $user.logged?
    {?( "{$role}" === "admin" && count({$items}) > 0 )?} admin {/?}
    [[product
      {$name} - {$price}
    product]]
    <div id="content">(( content ))</div>
    {{content
      Content goes here
    content}}
    {:customtags}[b]bold[/b]{:/customtags}
    {parse:beforeParse} {$name} {/parse:beforeParse}
    {strip}   a    b   {/strip}
    {txt} 80 => <h1>Title</h1>{/txt}
    {ignore} {$not_parsed} [$raw] {/ignore}
    <!--| [$friendly] |--> x <!--| [/$friendly] |-->
    <!-- plain html comment -->
<?
    $i = 0;
    foreach ($products as $p) { $i++; echo "$i\n"; }
?>
    [/$orphan]
  </body>
</html>
