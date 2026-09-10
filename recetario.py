UNIDADES_CANTIDAD = [
    "unidades",
    "gramos",
    "kilogramos",
    "mililitros",
    "litros"
]

ACRONIMOS = {
    "unidades":"uds",
    "gramos":"gr",
    "kilogramos":"kg",
    "mililitros":"ml",
    "litros":"l"
}

CATEGORIAS_POSIBLES = [
    "carne",
    "pescado",
    "carbohidrato",
    "especia",
    "verdura",
    "fruta",
    "salsa"
]

class Ingrediente():
    nombre:str
    
    def __init__(self,nombre="default",categoria="default"):
        self.nombre=nombre
        self.categoria = ""
        if categoria.lower() in CATEGORIAS_POSIBLES:
            self.categoria = categoria.lower
            
    def __str__(self):
        return self.nombre
        

class Receta():
    nombre:str
    lista_ingredientes:dict #{ingr1: (cantidad,unidad de medida), ingr2: (cantidad,unidad de medida)}
    lista_pasos:list #["paso1","paso2"]
    
    def __init__(self,nombre="default"):
        self.nombre = nombre
        self.lista_ingredientes = {}
        self.lista_pasos = []
    
    def añadir_ingrediente(self,ingrediente:Ingrediente,cantidad:int,tipo_cantidad:str="gramos"):
        if ACRONIMOS.get(tipo_cantidad.lower()) and cantidad > 0:    
            self.lista_ingredientes[ingrediente] = (cantidad,tipo_cantidad)
            return 0
        return 1
        
    def añadir_pasos(self,paso:str):
        self.lista_pasos.append(paso)
        return 0
        
    def __str__(self):
        ingredientes_output = ""
        for ing in self.lista_ingredientes.keys():
            cantidad = self.lista_ingredientes[ing][0]
            medida = self.lista_ingredientes[ing][1]
            ingredientes_output += "\t"+str(ing) + f", {cantidad} {ACRONIMOS.get(medida)}\n"
            # if i < len(self.lista_ingredientes):
            #     ingredientes_output += ", "
        
        pasos_output = ""
        for i in range(len(self.lista_pasos)):
            pasos_output += f"\t{i+1}º. "+self.lista_pasos[i]
            if i < len(self.lista_pasos):
                pasos_output += "\n"
                
        return f"receta: {self.nombre}\n\ningredientes:\n{ingredientes_output}\n\npasos:\n{pasos_output}"
    
receta1 = Receta("Arroz con pollo")
receta1.añadir_ingrediente(Ingrediente("pollo","Carne"),300)
receta1.añadir_ingrediente(Ingrediente("arroz","Carbohidrato"),200)
receta1.añadir_ingrediente(Ingrediente("vino","Salsa"),200,"mililitros")

receta1.añadir_pasos("Hacer el arroz en una olla")
receta1.añadir_pasos("Hacer el pollo en una sarten bien dorado")
receta1.añadir_pasos("Cortar el pollo y juntarlo con el arroz")

print(receta1)