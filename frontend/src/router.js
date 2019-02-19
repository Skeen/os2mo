import Vue from 'vue'
import Router from 'vue-router'
import employeeRouter from '@/views/employee/router'
import organisationRouter from '@/views/organisation/router'
import moduleRouters from '@/modules/router'

const MoBase = () => import('@/MoBase')
const LoginPage = () => import(/* webpackChunkName: "login" */ '@/views/login')
const Landing = () => import(/* webpackChunkName: "landingPage" */ '@/views/frontpage')
const PageNotFound = () => import('@/views/PageNotFound')

Vue.use(Router)

const GlobalRouter = [
  {
    path: '',
    name: 'Landing',
    component: Landing
  },
  {
    path: '/login',
    name: 'Login',
    component: LoginPage
  }
]

let BaseRouter = {
  path: '/',
  name: 'Base',
  component: MoBase,
  children: [
    employeeRouter,
    organisationRouter
  ]
}

/**
 * Add all routers from modules
 */
BaseRouter.children = BaseRouter.children.concat(moduleRouters)

const PageNotFoundRouter = {
  path: '*',
  name: 'PageNotFound',
  component: PageNotFound
}

/**
 * IMPORTANT! Page not found is last otherwise it overwrites ALL other routes
 */
BaseRouter.children.push(PageNotFoundRouter)

const routes = GlobalRouter.concat([BaseRouter])

export default new Router({
  mode: 'history',
  routes
})
