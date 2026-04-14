"use strict";

const admin = require("firebase-admin");
const { onDocumentWritten } = require("firebase-functions/v2/firestore");
const logger = require("firebase-functions/logger");
const sql = require("mssql");

admin.initializeApp();

const SQL_CONFIG = {
  server: process.env.DB_SERVER,
  database: process.env.DB_NAME,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  options: {
    encrypt: true,
    trustServerCertificate: false,
  },
  pool: {
    max: 5,
    min: 0,
    idleTimeoutMillis: 30000,
  },
};

const DEFAULT_CREATED_BY = Number(process.env.SCHEDULE_DEFAULT_CREATED_BY || "89126");
const DEFAULT_UPDATED_BY = Number(process.env.SCHEDULE_DEFAULT_UPDATED_BY || DEFAULT_CREATED_BY);

let poolPromise = null;

function getPool() {
  if (!poolPromise) {
    poolPromise = sql.connect(SQL_CONFIG);
  }
  return poolPromise;
}

function asString(value, fallback = "") {
  if (value === undefined || value === null) return fallback;
  return String(value).trim();
}

function asNullableString(value) {
  const v = asString(value);
  return v || null;
}

function asInt(value, fallback = null) {
  if (value === undefined || value === null || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function asBit(value) {
  return value === true || value === 1 || value === "1";
}

function scheduleDefaults(data) {
  return {
    center_cd: asString(data.center_cd || data.effective_center_cd),
    schedule_date: asString(data.schedule_date),
    schedule_type: asString(data.schedule_type || "1"),
    start_time: asString(data.startTime || data.start_time),
    end_time: asString(data.endTime || data.end_time),
    user_id: asInt(data.user_id),
    user_cd: asNullableString(data.user_cd),
    staff_user_id: asInt(data.staff_user_id),
    staff_user_cd: asNullableString(data.staff_user_cd),
    cost_type: asNullableString(data.cost_type),
    comment: asNullableString(data.content || data.comment),
    title: asNullableString(data.title || data.content),
    staff_center_cd: asNullableString(data.staff_center_cd || data.center_cd),
    multi_visitor: asNullableString(data.multi_visitor),
    service_code: asNullableString(data.service_code),
    addition_service: data.addition_service == null ? null : String(data.addition_service),
    service_name: asNullableString(data.service_name),
    kasan_service_name: asNullableString(data.kasan_service_name),
    nh_hospice_no: asInt(data.nh_hospice_no),
    nh_card_id: asNullableString(data.nh_card_id),
    nh_card_type: asInt(data.nh_card_type),
    nh_main_course_serial_no: asInt(data.nh_main_course_serial_no),
    nh_main_cancel_flg: asString(data.nh_main_cancel_flg, "0"),
    nh_sub_course_serial_no: asInt(data.nh_sub_course_serial_no),
    nh_sub_cancel_flg: asString(data.nh_sub_cancel_flg, "0"),
    nh_visit_number: asInt(data.nh_visit_number, 0),
    nh_content_json: asString(data.nh_content_json, "[]"),
    nh_record_coop_flg: asBit(data.nh_record_coop_flg),
    nh_comment: asNullableString(data.nh_comment),
    companion1_center_cd: asNullableString(data.companion1_center_cd),
    companion1_user_id: asInt(data.companion1_user_id),
    companion1_qualificstion: asNullableString(data.companion1_qualificstion),
    staff_qualification: asNullableString(data.staff_qualification),
    cancel_flg: "0",
    transfer_flg: "0",
    created_by: asInt(data.created_by, DEFAULT_CREATED_BY),
    updated_by: asInt(data.updated_by, DEFAULT_UPDATED_BY),
  };
}

async function markDoc(ref, patch) {
  await ref.set(patch, { merge: true });
}

async function insertSchedule(data) {
  const pool = await getPool();
  const tx = new sql.Transaction(pool);
  await tx.begin();
  try {
    const d = scheduleDefaults(data);
    const req = new sql.Request(tx);
    req.input("center_cd", sql.NChar(10), d.center_cd);
    req.input("schedule_date", sql.Date, d.schedule_date);
    req.input("schedule_type", sql.NVarChar(50), d.schedule_type);
    req.input("start_time", sql.NChar(5), d.start_time);
    req.input("end_time", sql.NChar(5), d.end_time);
    req.input("user_id", sql.Int, d.user_id);
    req.input("user_cd", sql.NChar(20), d.user_cd);
    req.input("staff_user_id", sql.Int, d.staff_user_id);
    req.input("staff_user_cd", sql.NChar(20), d.staff_user_cd);
    req.input("cost_type", sql.NChar(10), d.cost_type);
    req.input("comment", sql.NVarChar(sql.MAX), d.comment);
    req.input("created_by", sql.Int, d.created_by);
    req.input("updated_by", sql.Int, d.updated_by);
    req.input("cancel_flg", sql.NChar(1), d.cancel_flg);
    req.input("transfer_flg", sql.NChar(1), d.transfer_flg);
    req.input("title", sql.NVarChar(255), d.title);
    req.input("staff_center_cd", sql.Char(10), d.staff_center_cd);
    req.input("multi_visitor", sql.Char(1), d.multi_visitor);
    req.input("service_code", sql.VarChar(50), d.service_code);
    req.input("addition_service", sql.NVarChar(sql.MAX), d.addition_service);
    req.input("service_name", sql.NVarChar(255), d.service_name);
    req.input("kasan_service_name", sql.NVarChar(255), d.kasan_service_name);
    req.input("nh_hospice_no", sql.Int, d.nh_hospice_no);
    req.input("nh_card_id", sql.VarChar(100), d.nh_card_id);
    req.input("nh_card_type", sql.Int, d.nh_card_type);
    req.input("nh_main_course_serial_no", sql.Int, d.nh_main_course_serial_no);
    req.input("nh_main_cancel_flg", sql.VarChar(10), d.nh_main_cancel_flg);
    req.input("nh_sub_course_serial_no", sql.Int, d.nh_sub_course_serial_no);
    req.input("nh_sub_cancel_flg", sql.VarChar(10), d.nh_sub_cancel_flg);
    req.input("nh_visit_number", sql.Int, d.nh_visit_number);
    req.input("nh_content_json", sql.NVarChar(sql.MAX), d.nh_content_json);
    req.input("nh_record_coop_flg", sql.Bit, d.nh_record_coop_flg);
    req.input("nh_comment", sql.NVarChar(sql.MAX), d.nh_comment);
    req.input("companion1_center_cd", sql.Char(10), d.companion1_center_cd);
    req.input("companion1_user_id", sql.Int, d.companion1_user_id);
    req.input("companion1_qualificstion", sql.VarChar(50), d.companion1_qualificstion);
    req.input("staff_qualification", sql.VarChar(50), d.staff_qualification);
    const result = await req.query(`
      INSERT INTO schedule (
        center_cd, schedule_date, schedule_type, start_time, end_time,
        user_id, user_cd, staff_user_id, staff_user_cd, cost_type, comment,
        created_at, created_by, updated_at, updated_by, cancel_flg, transfer_flg,
        title, staff_center_cd, multi_visitor, service_code, addition_service,
        service_name, kasan_service_name, nh_hospice_no, nh_card_id, nh_card_type,
        nh_main_course_serial_no, nh_main_cancel_flg, nh_sub_course_serial_no,
        nh_sub_cancel_flg, nh_visit_number, nh_content_json, nh_record_coop_flg,
        nh_comment, companion1_center_cd, companion1_user_id, companion1_qualificstion,
        staff_qualification
      )
      OUTPUT INSERTED.serial_no
      VALUES (
        @center_cd, @schedule_date, @schedule_type, @start_time, @end_time,
        @user_id, @user_cd, @staff_user_id, @staff_user_cd, @cost_type, @comment,
        GETDATE(), @created_by, GETDATE(), @updated_by, @cancel_flg, @transfer_flg,
        @title, @staff_center_cd, @multi_visitor, @service_code, @addition_service,
        @service_name, @kasan_service_name, @nh_hospice_no, @nh_card_id, @nh_card_type,
        @nh_main_course_serial_no, @nh_main_cancel_flg, @nh_sub_course_serial_no,
        @nh_sub_cancel_flg, @nh_visit_number, @nh_content_json, @nh_record_coop_flg,
        @nh_comment, @companion1_center_cd, @companion1_user_id, @companion1_qualificstion,
        @staff_qualification
      );
    `);
    await tx.commit();
    return result.recordset[0].serial_no;
  } catch (err) {
    await tx.rollback();
    throw err;
  }
}

async function updateSchedule(serialNo, data) {
  const pool = await getPool();
  const d = scheduleDefaults(data);
  const req = pool.request();
  req.input("serial_no", sql.BigInt, Number(serialNo));
  req.input("center_cd", sql.NChar(10), d.center_cd);
  req.input("schedule_date", sql.Date, d.schedule_date);
  req.input("schedule_type", sql.NVarChar(50), d.schedule_type);
  req.input("start_time", sql.NChar(5), d.start_time);
  req.input("end_time", sql.NChar(5), d.end_time);
  req.input("user_id", sql.Int, d.user_id);
  req.input("user_cd", sql.NChar(20), d.user_cd);
  req.input("staff_user_id", sql.Int, d.staff_user_id);
  req.input("staff_user_cd", sql.NChar(20), d.staff_user_cd);
  req.input("cost_type", sql.NChar(10), d.cost_type);
  req.input("comment", sql.NVarChar(sql.MAX), d.comment);
  req.input("updated_by", sql.Int, d.updated_by);
  req.input("title", sql.NVarChar(255), d.title);
  req.input("staff_center_cd", sql.Char(10), d.staff_center_cd);
  req.input("multi_visitor", sql.Char(1), d.multi_visitor);
  req.input("service_code", sql.VarChar(50), d.service_code);
  req.input("addition_service", sql.NVarChar(sql.MAX), d.addition_service);
  req.input("service_name", sql.NVarChar(255), d.service_name);
  req.input("kasan_service_name", sql.NVarChar(255), d.kasan_service_name);
  req.input("nh_hospice_no", sql.Int, d.nh_hospice_no);
  req.input("nh_card_id", sql.VarChar(100), d.nh_card_id);
  req.input("nh_card_type", sql.Int, d.nh_card_type);
  req.input("nh_main_course_serial_no", sql.Int, d.nh_main_course_serial_no);
  req.input("nh_main_cancel_flg", sql.VarChar(10), d.nh_main_cancel_flg);
  req.input("nh_sub_course_serial_no", sql.Int, d.nh_sub_course_serial_no);
  req.input("nh_sub_cancel_flg", sql.VarChar(10), d.nh_sub_cancel_flg);
  req.input("nh_visit_number", sql.Int, d.nh_visit_number);
  req.input("nh_content_json", sql.NVarChar(sql.MAX), d.nh_content_json);
  req.input("nh_record_coop_flg", sql.Bit, d.nh_record_coop_flg);
  req.input("nh_comment", sql.NVarChar(sql.MAX), d.nh_comment);
  req.input("companion1_center_cd", sql.Char(10), d.companion1_center_cd);
  req.input("companion1_user_id", sql.Int, d.companion1_user_id);
  req.input("companion1_qualificstion", sql.VarChar(50), d.companion1_qualificstion);
  req.input("staff_qualification", sql.VarChar(50), d.staff_qualification);
  await req.query(`
    UPDATE schedule
    SET center_cd = @center_cd,
        schedule_date = @schedule_date,
        schedule_type = @schedule_type,
        start_time = @start_time,
        end_time = @end_time,
        user_id = @user_id,
        user_cd = @user_cd,
        staff_user_id = @staff_user_id,
        staff_user_cd = @staff_user_cd,
        cost_type = @cost_type,
        comment = @comment,
        updated_at = GETDATE(),
        updated_by = @updated_by,
        title = @title,
        staff_center_cd = @staff_center_cd,
        multi_visitor = @multi_visitor,
        service_code = @service_code,
        addition_service = @addition_service,
        service_name = @service_name,
        kasan_service_name = @kasan_service_name,
        nh_hospice_no = @nh_hospice_no,
        nh_card_id = @nh_card_id,
        nh_card_type = @nh_card_type,
        nh_main_course_serial_no = @nh_main_course_serial_no,
        nh_main_cancel_flg = @nh_main_cancel_flg,
        nh_sub_course_serial_no = @nh_sub_course_serial_no,
        nh_sub_cancel_flg = @nh_sub_cancel_flg,
        nh_visit_number = @nh_visit_number,
        nh_content_json = @nh_content_json,
        nh_record_coop_flg = @nh_record_coop_flg,
        nh_comment = @nh_comment,
        companion1_center_cd = @companion1_center_cd,
        companion1_user_id = @companion1_user_id,
        companion1_qualificstion = @companion1_qualificstion,
        staff_qualification = @staff_qualification
    WHERE serial_no = @serial_no
  `);
}

async function cancelSchedule(serialNo) {
  const pool = await getPool();
  await pool.request()
    .input("serial_no", sql.BigInt, Number(serialNo))
    .query(`
      UPDATE schedule
      SET cancel_flg = '1',
          deleted_at = GETDATE(),
          updated_at = GETDATE(),
          updated_by = ${DEFAULT_UPDATED_BY}
      WHERE serial_no = @serial_no
    `);
}

exports.syncScheduleWriteback = onDocumentWritten("schedules/{scheduleId}", async (event) => {
  const before = event.data.before.exists ? event.data.before.data() : null;
  const after = event.data.after.exists ? event.data.after.data() : null;
  const afterRef = event.data.after.ref;

  if (!after) {
    if (before && before.serial_no) {
      await cancelSchedule(before.serial_no);
      logger.info("schedule canceled in SQL", { serial_no: before.serial_no });
    }
    return;
  }

  if (after.writeback_status !== "pending") {
    return;
  }

  try {
    const serialNo = after.serial_no ? Number(after.serial_no) : null;
    let finalSerialNo = serialNo;
    if (finalSerialNo) {
      await updateSchedule(finalSerialNo, after);
    } else {
      finalSerialNo = await insertSchedule(after);
    }

    const canonicalId = `sql_${finalSerialNo}`;
    const canonicalRef = admin.firestore().collection("schedules").doc(canonicalId);
    const canonicalDoc = {
      ...after,
      serial_no: finalSerialNo,
      id: finalSerialNo,
      source: "sql_schedule",
      writeback_target: "sql_schedule",
      writeback_status: "synced",
      last_sql_writeback_at: admin.firestore.FieldValue.serverTimestamp(),
      last_sql_error: admin.firestore.FieldValue.delete(),
    };

    await canonicalRef.set(canonicalDoc, { merge: true });

    if (afterRef.id !== canonicalId) {
      await afterRef.delete();
    } else {
      await markDoc(afterRef, {
        serial_no: finalSerialNo,
        id: finalSerialNo,
        source: "sql_schedule",
        writeback_target: "sql_schedule",
        writeback_status: "synced",
        last_sql_writeback_at: admin.firestore.FieldValue.serverTimestamp(),
        last_sql_error: admin.firestore.FieldValue.delete(),
      });
    }

    logger.info("schedule writeback synced", { serial_no: finalSerialNo, docId: canonicalId });
  } catch (err) {
    logger.error("schedule writeback failed", err);
    await markDoc(afterRef, {
      writeback_status: "error",
      last_sql_error: String(err.message || err),
      last_sql_error_at: admin.firestore.FieldValue.serverTimestamp(),
    });
    throw err;
  }
});
