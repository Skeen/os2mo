import { Selector } from 'testcafe'
import { baseURL } from './support'

let moment = require('moment')

fixture('Organisation test')
  .page(`${baseURL}/organisation`)

const dialog = Selector('#orgUnitMove')

const unitInput = dialog.find('input[data-vv-as="Enhed"]')

const parentInput = dialog.find('.parentUnit input[data-vv-as="Enhed"]')

const fromInput = dialog.find('.moveDate input.form-control')

test('Workflow: move unit', async t => {
  let today = moment()

  await t
    .setTestSpeed(0.8)

    .hover('#mo-workflow', {offsetX: 10, offsetY: 90})
    .click('.btn-unit-move')

    .expect(dialog.exists).ok('Opened dialog')

    .click(unitInput)
    .click(dialog.find('li .item .link-color'))

    .click(parentInput)
    .click(dialog.find('.parentUnit li .item .link-color'))

    .click(fromInput)
    .hover(dialog.find('.vdp-datepicker .day:not(.blank)')
           .withText(today.date().toString()))
    .click(dialog.find('.vdp-datepicker .day:not(.blank)')
           .withText(today.date().toString()))
    .expect(fromInput.value).eql(today.format('DD-MM-YYYY'))

    .click(dialog.find('.btn-primary'))

    .expect(Selector('#orgUnitCreate').exists).notOk()
})
