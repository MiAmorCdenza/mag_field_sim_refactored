! parabmod_api.f90 —— 把 Alexeev 抛物面模型(parabmod.for)包成 C 可调用的 DLL。
!
! 为什么走 DLL + ctypes 而不是 f2py:
!   f2py 2.x 在 Python>=3.12 上改用 meson 后端(--fcompiler 失效),
!   且包装 parabmod.for 里的 Bessel 辅助例程时内部报 KeyError('besj0');
!   普通 DLL 不绑 Python 版本、便携包里只多一个 .dll + 4 个 gfortran 运行库,
!   并且**批量接口**把整块点阵一次算完(逐点调 Python 会慢一个数量级)。
!
! 接口(与 parabmod.for 的 a2000 一致,点阵按 Fortran 列主序 = C 的 (n,3)):
!   parab_point(ut,iy,mo,id,ro,v,bimf,dst,al,x(3) -> bm(3), bb(7,3))
!   parab_batch(n, xyz(3,n), …, bm(3,n), bb(7,3,n))
!   bb 行:1 偶极 / 2 环电流 / 3 尾电流 / 4 CF 屏蔽偶极 / 5 CF 屏蔽环电流
!          / 6 Region-1 FAC / 7 穿透 IMF
!
! 编译(见 scripts/build_paraboloid.ps1):
!   gfortran -shared -O2 -o parabmod.dll parabmod.for parabmod_api.f90

subroutine parab_point(ut, iy, mo, id, ro, v, bimf, dst, al, x, bm, bb) &
        bind(C, name="parab_point")
    use iso_c_binding
    implicit none
    real(c_double), value :: ut, ro, v, dst, al
    real(c_double) :: bimf(3)        ! IMF 三分量(GSM, nT)—— 不是标量 Bz
    integer(c_int), value :: iy, mo, id
    real(c_double) :: x(3), bm(3), bb(7, 3)
    call a2000(ut, iy, mo, id, ro, v, bimf, dst, al, x, bm, bb)
end subroutine parab_point

subroutine parab_batch(n, xyz, ut, iy, mo, id, ro, v, bimf, dst, al, &
                       bm_all, bb_all) bind(C, name="parab_batch")
    use iso_c_binding
    implicit none
    integer(c_int), value :: n, iy, mo, id
    real(c_double), value :: ut, ro, v, dst, al
    real(c_double) :: bimf(3)        ! IMF 三分量(GSM, nT)—— 不是标量 Bz
    real(c_double) :: xyz(3, n), bm_all(3, n), bb_all(7, 3, n)
    real(c_double) :: x(3), bm(3), bb(7, 3)
    integer :: i
    do i = 1, n
        x(1) = xyz(1, i)
        x(2) = xyz(2, i)
        x(3) = xyz(3, i)
        call a2000(ut, iy, mo, id, ro, v, bimf, dst, al, x, bm, bb)
        bm_all(1, i) = bm(1)
        bm_all(2, i) = bm(2)
        bm_all(3, i) = bm(3)
        bb_all(1:7, 1, i) = bb(1:7, 1)
        bb_all(1:7, 2, i) = bb(1:7, 2)
        bb_all(1:7, 3, i) = bb(1:7, 3)
    end do
end subroutine parab_batch
