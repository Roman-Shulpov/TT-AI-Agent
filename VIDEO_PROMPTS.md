# Video prompts

Use these prompts from `start.cmd`. Close the previous browser window before starting the next recording.

## 1. TodoMVC active tasks

```text
Open https://demo.playwright.dev/todomvc/. Add three tasks: Read README, Run tests, Record demo. Mark Read README completed. Show only active tasks and report their names and count. Leave the browser on the final result.
```

Expected final screen: `Run tests`, `Record demo`, `2 items left`.

## 2. Books comparison

```text
Open https://books.toscrape.com/. Find the Travel category. Open the first two book detail pages, compare their full titles and prices, and report which book is cheaper and by how much. Do not purchase anything. Leave the browser on the final result.
```

Expected answer: `It's Only the Himalayas` is cheaper than `Full Moon over Noah's Ark: An Odyssey to Mount Ararat and Beyond` by `£4.26`.

## 3. TodoMVC completed tasks

```text
Open https://demo.playwright.dev/todomvc/. Add two tasks: Prepare presentation and Send project. Mark Prepare presentation completed. Mark Send project completed. Show only completed tasks and report their names and count. Leave the browser on the final result.
```

Expected final screen: `Prepare presentation`, `Send project`, `0 items left`, both tasks checked on the Completed filter.

## 4. Food order demo

```text
Open https://dodopizza.ru/barnaul/product/chipsi-picca. Read the product card for Chipsi pizza. Report the pizza name, size, weight, ingredients, and price. Do not add anything to the cart, do not checkout, and do not pay. Leave the browser on the product card.
```

Expected final screen: Chipsi pizza product card is open. No cart, no checkout, no payment, no personal data.
