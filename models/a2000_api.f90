! a2000_api.f90 —— 把 IRBEM 的标准双精度 A2000(抛物面/CPMOD)包成 C 可调用的 DLL。
!
! 与第一版(包装竞赛项目的 parabmod.for)的关键区别:
!   1) 源码换成 IRBEM 的 Alexeev2000.f(显式 DIMENSION bimf(3),REAL*8 接口,带 ifail),
!      不再靠 -fallow-argument-mismatch 兜秩不匹配;
!   2) **两段式**:submod() 把空间天气参数算成 par(1..10) 只做一次(每张图一次),
!      然后逐点调 A_field() —— 这正是模型自己的结构(A_field 只依赖 par),
!      比每个点重算一遍 submod 快得多,而且能把 par 直接给 UI 显示;
!   3) 时间通过模型的 COMMON /a2000_time/ 传入(IRBEM 版就是这么取时间的)。
!
! par(1..10) 定义(见源码 submod 头注释):
!   1 偶极倾角(°)  2 赤道偶极场(nT)  3 尾瓣磁通(Wb)  4 环电流最大强度(nT)
!   5 Region-1 FAC 总电流(MA)  6 磁层顶驻点(Re)  7 尾电流内边界(Re)  8-10 穿透 IMF(nT)
!
! 编译(scripts/build_a2000.ps1):
!   gfortran -shared -O2 -std=legacy -fdefault-real-8 -fdefault-double-8 \
!            -o models\a2000.dll models\a2000_irbem.f models\a2000_api.f90

subroutine a2000_set_time(ut, iyear, imonth, iday) bind(C, name="a2000_set_time")
    use iso_c_binding
    implicit none
    real(c_double), value :: ut
    integer(c_int), value :: iyear, imonth, iday
    real*8 a2000_ut
    integer*4 a2000_iyear, a2000_imonth, a2000_iday
    common /a2000_time/ a2000_ut, a2000_iyear, a2000_imonth, a2000_iday
    a2000_ut = ut
    a2000_iyear = iyear
    a2000_imonth = imonth
    a2000_iday = iday
end subroutine a2000_set_time

subroutine a2000_params(ro, v, bimf, dst, al, par, ifail) &
        bind(C, name="a2000_params")
    use iso_c_binding
    implicit none
    real(c_double), value :: ro, v, dst, al
    real(c_double) :: bimf(3), par(10)
    integer(c_int) :: ifail
    real*8 a2000_ut
    integer*4 a2000_iyear, a2000_imonth, a2000_iday
    common /a2000_time/ a2000_ut, a2000_iyear, a2000_imonth, a2000_iday
    ifail = 0
    if (ro <= 0.0d0 .or. v <= 0.0d0) then
        ifail = 1                     ! 太阳风参数非法(避免除零/负数开方)
        return
    end if
    call submod(a2000_ut, a2000_iyear, a2000_imonth, a2000_iday, &
                ro, v, bimf, dst, al, par)
end subroutine a2000_params

subroutine a2000_field(par, x, bm, bb) bind(C, name="a2000_field")
    use iso_c_binding
    implicit none
    real(c_double) :: par(10), x(3), bm(3), bb(7, 3)
    call A_field(x, par, bm, bb)
end subroutine a2000_field

! 批量:同一组 par 下算 n 个点(Fortran 列主序 (3,n) = C 的 (n,3))
subroutine a2000_batch(par, n, xyz, bm_all, bb_all) &
        bind(C, name="a2000_batch")
    use iso_c_binding
    implicit none
    real(c_double) :: par(10), xyz(3, n), bm_all(3, n), bb_all(7, 3, n)
    integer(c_int), value :: n
    real*8 x(3), bm(3), bb(7, 3)
    integer :: i
    do i = 1, n
        x(1) = xyz(1, i)
        x(2) = xyz(2, i)
        x(3) = xyz(3, i)
        call A_field(x, par, bm, bb)
        bm_all(1, i) = bm(1)
        bm_all(2, i) = bm(2)
        bm_all(3, i) = bm(3)
        bb_all(1:7, 1, i) = bb(1:7, 1)
        bb_all(1:7, 2, i) = bb(1:7, 2)
        bb_all(1:7, 3, i) = bb(1:7, 3)
    end do
end subroutine a2000_batch

! 分源开关(PSTATUS:源码里唯一给 COMMON/SM/ 赋值的地方)。
! ⚠ 必须初始化:不调用它时 SSD/SSR/SMD/SMR/SS1/SIMF 全为 0,
!   分源行会被抹掉(实测 bb(1) 偶极行只剩 149 nT、bb(5) 变成整块屏蔽场),
!   虽然总场仍对,但分源/开关功能全废。
! 参数:1=开 0=关。官方"全开"= pstatus(1,1,1,1,1,1,1)
subroutine a2000_set_sources(x1, x2, x3, x4, x5, x6, x7) &
        bind(C, name="a2000_set_sources")
    use iso_c_binding
    implicit none
    real(c_double), value :: x1, x2, x3, x4, x5, x6, x7
    call PSTATUS(x1, x2, x3, x4, x5, x6, x7)
end subroutine a2000_set_sources