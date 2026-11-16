# SPDX-License-Identifier: GPL-3.0-or-later
"""Ölçü Ustası — çok parçalı modelleri tek bütün olarak ölç ve ölçekle.

  * Birden çok seçili nesne (ve alt nesneleri, koleksiyon örnekleri) tek bütün gibi
    davranır; ölçek yalnız köklere uygulanır, aralarındaki ilişki hiç bozulmaz.
  * Köşe / kenar / kenar ortası / yüzey / dik / sınır kutusu / köken yakalama;
    mesh yoğunluğundan bağımsız akıcı (BVH ışın örnekleme).
  * X/Y/Z eksen ve düzlem izdüşümlü ölçüm, referans ölçüye eşitleme, sabit ölçüler.
  * Kutu tutamaçlarıyla sürükleyerek ölçekleme, aktif nesneye sığdırma,
    ölçeği veriye güvenle uygulama.
"""
import bpy

from . import ops_misc, pins, props, ui
from .op_cage import OU_OT_cage
from .op_measure import OU_OT_measure

_ops = (OU_OT_measure, OU_OT_cage) + ops_misc.classes


def register():
    props.register()
    for c in _ops:
        bpy.utils.register_class(c)
    ops_misc.register_dims()
    ui.register()
    pins.register()


def unregister():
    pins.unregister()
    ui.unregister()
    ops_misc.unregister_dims()
    for c in reversed(_ops):
        bpy.utils.unregister_class(c)
    props.unregister()
