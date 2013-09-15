# -*- coding: utf-8 -*-
import psycopg2
import psycopg2.extras
import unittest
import cliente as cl
import moduloCliente as mc
import consumos as con
import database as db
import dbparams

class Factura:
    def __init__(self, idProducto):                   
        self.idProducto = idProducto
        self.cliente = self.buscarCliente()
        self.mesFacturacion = self.buscarMes()
        self.anioFacturacion = self.buscarAnio()
        self.listaConsumos = self.buscarConsumos()
        self.montoTotalCobrar = self.totalCobrar()

    def buscarCliente(self):
        try:
            cedula = self.buscarCedula()
            cliente = mc.busquedaCliente(cedula);
            return cliente
        except Exception, e:
            print "Error buscando la informacion del cliente", e
            
    def buscarCedula(self):
        try:
            conexion = db.operacion ("Buscamos la cedula del cliente",
                                    """SELECT cl.cedula FROM producto AS pr, cliente as cl 
                                       WHERE cl.cedula = pr.cedula AND numserie =\'%s\';""" %
                                       self.idProducto, dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
            resultado = conexion.execute()
            return str(resultado[0][0])
        except Exception, e:
            print "Error buscando la cedula del cliente", e
    
    def buscarMes(self):
        return str(raw_input("Por favor, introduzca el mes de facturacion "))
    
    def buscarAnio(self):
        return str(raw_input("Por favor, introduzca el año de facturacion "))

    def buscarConsumos(self):
        conexion = db.operacion("Buscamos todos los consumos asociados a un producto",
                             """ SELECT to_char(con.fecha, 'DD MM YYYY'), serv.nombreserv, con.cantidad
                                 FROM consume AS con, servicio AS serv 
                                 WHERE con.numserie = \'%s\'  AND to_number(to_char(con.fecha, 'MM'),'9999999') = %s 
                                 AND serv.codserv = con.codserv""" % (self.idProducto, self.mesFacturacion),
                                 dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
     
        return conexion.execute()

    def totalCobrar(self):
        conexion = db.operacion("Buscamos el codigo del plan asociado al producto",
                                """SELECT codplan FROM afilia WHERE numserie = \'%s\'""" % self.idProducto,
                                dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
        
        resultado = conexion.execute()
        
        if len(resultado) == 0:
            conexion = db.operacion("Buscamos el codigo del plan asociado al producto",
                                    """SELECT codplan FROM activa WHERE numserie = \'%s\'""" % self.idProducto,
                                    dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
            resultado = conexion.execute()

        codplan = resultado[0][0]

        #Buscamos la renta del plan que se va a cobrar al producto.      
        conexion = db.operacion("Buscamos la renta del plan que se va a cobrar al producto",
                                """SELECT renta_basica FROM plan WHERE codplan = %s""" % codplan,
                                dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
        resultado = conexion.execute()
        renta = int(resultado[0][0])
        
        #Buscamos la suma de todos los consumos por servicio hechos por el producto en el año y mes introducidos por el usuario.
        #Lo guardamos en un diccionario donde la clave es el codigo del servicio.
        conexion = db.operacion("Buscamos la suma de todos los consumos por servicio",
                                """SELECT con.codserv, sum(con.cantidad) AS total FROM consume AS con 
                                WHERE con.numserie = \'%s\' AND 
                                to_char(con.fecha, 'MM YYYY') = \'%s\' GROUP BY (con.codserv)""" %
                                (self.idProducto, self.mesFacturacion + " " + self.anioFacturacion),
                                dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
       
        resultado = conexion.execute()
        
        totalConsumido = {}
        for row in resultado:
                totalConsumido[row[0]] = int(row[1])
        
        #Buscamos los servicios ofrecidos por el plan y la cantidad y tarifa ofrecidos por este. 
        #El resultado se guarda en un diccionario
        #donde la clave es el codigo del servicio.
        
        conexion = db.operacion("Buscamos los servicios ofrecidos por el plan, ademas de la cantidad y tarifa ofrecidos por este",
                                """SELECT inc.codserv, inc.cantidad, inc.tarifa FROM incluye AS inc, servicio AS serv 
                                WHERE inc.codplan =  %s and serv.codserv = inc.codserv;""" % codplan,
                                dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
        
        resultado = conexion.execute()       
         
        totalPlan = {}
        
        for row in resultado:
            totalPlan[row[0]] = [row[1], row[2]]
                
        #Se busca si el producto este asociado a algun paquete. De estarlo, las cantidades de servicio ofrecidas se agregan al
        #diccionario de los servicios ofrecidos por el plan.
        conexion = db.operacion("Paquetes a los que esta asociado un producto",
                                """SELECT codserv, cantidad, costo FROM contrata NATURAL JOIN contiene NATURAL JOIN servicio 
                                WHERE numserie = \'%s\'""" % self.idProducto,
                                dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
        
        resultado = conexion.execute()
        for row in resultado:
            codserv = row[0]
            if totalPlan.has_key(codserv):
                totalPlan[codserv][0] = totalPlan[codserv][0] + int(row[1])
            else:
                totalPlan[codserv] = [int(row[1]), row[2]]
        
        #Se busca el costo total de todos los paquetes a los que esta suscrito el producto. El resultado se almacena
        #en el total a cobrar.
        conexion = db.operacion("Costo total de todos los paquetes",
                                """SELECT sum(precio) FROM contrata NATURAL JOIN paquete 
                                WHERE numserie = \'%s\' GROUP BY(contrata.numserie)""" % self.idProducto,
                                dbparams.dbname,dbparams.dbuser,dbparams.dbpass)
        
        resultado = conexion.execute()
        if len(resultado) == 0:
            total = 0
        else:
            total = int(resultado[0][0])
        
        #Se verifica la suma de los consumos por servicio del producto, si excede el valor ofrecido por el plan/paquete
        #entonces se cobra lo indicado por el plan. En caso que el serivicio sea ofrecido por un paquete, se cobra por exceso
        #el costo del servicio.
        for con in totalConsumido.keys():
            consumido = totalConsumido[con]
            limite = totalPlan[con][0]
            if consumido > limite:
                total = total + (consumido - limite) * totalPlan[con][1]
        
        return total + renta

if __name__ == '__main__':
    factura = Factura("CBZ27326")
    for row in factura.listaConsumos:
        print row
    
    print factura.montoTotalCobrar