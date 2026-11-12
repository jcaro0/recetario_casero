for recipe in \
  '{"name":"4Lentejas estofadas","type":"comida","ingredients":[{"name":"4Lentejas","qty":400,"unit":"g"},{"name":"4Zanahoria","qty":4,"unit":"uds"},{"name":"4Patata","qty":1,"unit":"uds"},{"name":"4Cebolla","qty":1,"unit":"uds"},{"name":"4Aceite de oliva","qty":4,"unit":"cda"}]}' \
  '{"name":"4Pollo al horno con patatas","type":"comida","ingredients":[{"name":"4Pechuga de pollo","qty":500,"unit":"g"},{"name":"4Patata","qty":4,"unit":"uds"},{"name":"4Ajo","qty":4,"unit":"uds"},{"name":"4Aceite de oliva","qty":4,"unit":"cda"},{"name":"4Sal","qty":null,"unit":null}]}' \
  '{"name":"4Pasta a la boloñesa","type":"comida","ingredients":[{"name":"4Macarrones","qty":450,"unit":"g"},{"name":"4Carne picada","qty":400,"unit":"g"},{"name":"4Tomate triturado","qty":400,"unit":"g"},{"name":"4Cebolla","qty":1,"unit":"uds"},{"name":"4Zanahoria","qty":1,"unit":"uds"}]}' \
  '{"name":"4Arroz con verduras y pollo","type":"comida","ingredients":[{"name":"4Arroz","qty":400,"unit":"g"},{"name":"4Pechuga de pollo","qty":400,"unit":"g"},{"name":"4Pimiento rojo","qty":1,"unit":"uds"},{"name":"4Calabacín","qty":1,"unit":"uds"},{"name":"4Caldo de pollo","qty":600,"unit":"ml"}]}' \
  '{"name":"4Salmón a la plancha con ensalada","type":"comida","ingredients":[{"name":"4Lomo de salmón","qty":4,"unit":"uds"},{"name":"4Lechuga","qty":1,"unit":"uds"},{"name":"4Tomate","qty":4,"unit":"uds"},{"name":"4Aceite de oliva","qty":1,"unit":"cda"}]}' \
  '{"name":"4Tortilla de patatas","type":"cena","ingredients":[{"name":"4Huevo","qty":5,"unit":"uds"},{"name":"4Patata","qty":4,"unit":"uds"},{"name":"4Cebolla","qty":1,"unit":"uds"},{"name":"4Aceite de oliva","qty":4,"unit":"cda"},{"name":"4Sal","qty":null,"unit":null}]}' \
  '{"name":"4Crema de calabacín","type":"cena","ingredients":[{"name":"4Calabacín","qty":4,"unit":"uds"},{"name":"4Patata","qty":1,"unit":"uds"},{"name":"4Cebolla","qty":0.5,"unit":"uds"},{"name":"4Leche","qty":100,"unit":"ml"},{"name":"4Aceite de oliva","qty":1,"unit":"cda"}]}' \
  '{"name":"4Revuelto de champiñones y gambas","type":"cena","ingredients":[{"name":"4Huevo","qty":4,"unit":"uds"},{"name":"4Champiñones","qty":400,"unit":"g"},{"name":"4Gambas peladas","qty":150,"unit":"g"},{"name":"4Ajo","qty":4,"unit":"uds"}]}' \
  '{"name":"4Ensalada César con pollo","type":"cena","ingredients":[{"name":"4Lechuga","qty":1,"unit":"uds"},{"name":"4Pechuga de pollo","qty":450,"unit":"g"},{"name":"4Queso parmesano","qty":50,"unit":"g"},{"name":"4Pan tostado","qty":1,"unit":"taza"}]}' \
  '{"name":"4Tostadas de aguacate y huevo","type":"cena","ingredients":[{"name":"4Pan de molde","qty":4,"unit":"uds"},{"name":"4Aguacate","qty":1,"unit":"uds"},{"name":"4Huevo","qty":4,"unit":"uds"},{"name":"4Tomate","qty":1,"unit":"uds"}]}'
do
  curl -s -X POST http://localhost:8000/recipes \
    -H "Content-Type: application/json" \
    -d "$recipe" > /dev/null
done && curl -X POST http://localhost:8000/menu/generate