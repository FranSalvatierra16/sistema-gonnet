class Reserva(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE)
    vendedor = models.ForeignKey(Vendedor, on_delete=models.CASCADE)  # Asegúrate de que sea Vendedor y no User
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)
    # ... otros campos 