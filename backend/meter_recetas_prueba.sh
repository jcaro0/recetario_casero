for recipe in \
  '{"name":"Lentejas estofadas","type":"comida","ingredients":[{"name":"Lentejas","qty":300,"unit":"g"},{"name":"Zanahoria","qty":2,"unit":"uds"},{"name":"Patata","qty":1,"unit":"uds"},{"name":"Cebolla","qty":1,"unit":"uds"},{"name":"Aceite de oliva","qty":2,"unit":"cda"}]}' \
  '{"name":"Pollo al horno con patatas","type":"comida","ingredients":[{"name":"Pechuga de pollo","qty":500,"unit":"g"},{"name":"Patata","qty":3,"unit":"uds"},{"name":"Ajo","qty":2,"unit":"uds"},{"name":"Aceite de oliva","qty":2,"unit":"cda"},{"name":"Sal","qty":null,"unit":null}]}' \
  '{"name":"Pasta a la boloñesa","type":"comida","ingredients":[{"name":"Macarrones","qty":350,"unit":"g"},{"name":"Carne picada","qty":400,"unit":"g"},{"name":"Tomate triturado","qty":400,"unit":"g"},{"name":"Cebolla","qty":1,"unit":"uds"},{"name":"Zanahoria","qty":1,"unit":"uds"}]}' \
  '{"name":"Arroz con verduras y pollo","type":"comida","ingredients":[{"name":"Arroz","qty":300,"unit":"g"},{"name":"Pechuga de pollo","qty":300,"unit":"g"},{"name":"Pimiento rojo","qty":1,"unit":"uds"},{"name":"Calabacín","qty":1,"unit":"uds"},{"name":"Caldo de pollo","qty":600,"unit":"ml"}]}' \
  '{"name":"Salmón a la plancha con ensalada","type":"comida","ingredients":[{"name":"Lomo de salmón","qty":2,"unit":"uds"},{"name":"Lechuga","qty":1,"unit":"uds"},{"name":"Tomate","qty":2,"unit":"uds"},{"name":"Aceite de oliva","qty":1,"unit":"cda"}]}' \
  '{"name":"Tortilla de patatas","type":"cena","ingredients":[{"name":"Huevo","qty":5,"unit":"uds"},{"name":"Patata","qty":3,"unit":"uds"},{"name":"Cebolla","qty":1,"unit":"uds"},{"name":"Aceite de oliva","qty":3,"unit":"cda"},{"name":"Sal","qty":null,"unit":null}]}' \
  '{"name":"Crema de calabacín","type":"cena","ingredients":[{"name":"Calabacín","qty":2,"unit":"uds"},{"name":"Patata","qty":1,"unit":"uds"},{"name":"Cebolla","qty":0.5,"unit":"uds"},{"name":"Leche","qty":100,"unit":"ml"},{"name":"Aceite de oliva","qty":1,"unit":"cda"}]}' \
  '{"name":"Revuelto de champiñones y gambas","type":"cena","ingredients":[{"name":"Huevo","qty":4,"unit":"uds"},{"name":"Champiñones","qty":200,"unit":"g"},{"name":"Gambas peladas","qty":150,"unit":"g"},{"name":"Ajo","qty":2,"unit":"uds"}]}' \
  '{"name":"Ensalada César con pollo","type":"cena","ingredients":[{"name":"Lechuga","qty":1,"unit":"uds"},{"name":"Pechuga de pollo","qty":250,"unit":"g"},{"name":"Queso parmesano","qty":50,"unit":"g"},{"name":"Pan tostado","qty":1,"unit":"taza"}]}' \
  '{"name":"Tostadas de aguacate y huevo","type":"cena","ingredients":[{"name":"Pan de molde","qty":4,"unit":"uds"},{"name":"Aguacate","qty":1,"unit":"uds"},{"name":"Huevo","qty":2,"unit":"uds"},{"name":"Tomate","qty":1,"unit":"uds"}]}'
do
  curl -s -X POST http://localhost:8000/recipes \
    -H "Content-Type: application/json" \
    -d "$recipe" > /dev/null
done && curl -X POST http://localhost:8000/menu/generate